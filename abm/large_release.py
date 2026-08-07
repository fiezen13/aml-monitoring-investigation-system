"""Bounded-memory orchestration for multi-gigabyte ABM-BANK releases."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from abm.exporters.release import load_release, verify_manifest
from abm.registry import ParameterRegistry, SimulationConfig
from abm.release import build_release
from abm.validation.release import validate_world


def build_large_release(
    config_path: str | Path = "abm/configs/large.yaml",
    output_root: str | Path = "data/generated",
    *,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    base = SimulationConfig.load(config_path)
    shard_count = int(raw["shard_count"])
    workers = int(raw["parallel_workers"])
    minimum_bytes = int(raw["minimum_release_bytes"])
    if shard_count < 2:
        raise ValueError("large release requires at least two shards")
    if workers < 1 or workers > 12:
        raise ValueError("parallel_workers must be in [1, 12]")
    if minimum_bytes < 2_000_000_000:
        raise ValueError("large release minimum_release_bytes must be at least 2 GB")

    output = Path(output_root)
    release_dir = output / base.release_name
    staging = output / f".{base.release_name}.building"
    if release_dir.exists():
        if not overwrite:
            raise FileExistsError(f"large release already exists: {release_dir}")
        _clear_exact_directory(release_dir, output, base.release_name)
    if staging.exists():
        if overwrite:
            _clear_exact_directory(staging, output, f".{base.release_name}.building")
    staging.mkdir(parents=True, exist_ok=True)

    futures = {}
    results: dict[int, dict[str, Any]] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for index in range(shard_count):
            shard_root = staging / f"shard-{index:03d}"
            existing_manifest = shard_root / base.release_name / "manifest.json"
            if existing_manifest.is_file():
                results[index] = _existing_shard_result(shard_root / base.release_name, index)
                continue
            if shard_root.exists():
                _clear_exact_directory(shard_root, staging, f"shard-{index:03d}")
            future = executor.submit(_build_one_shard, base, shard_root, index)
            futures[future] = index
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    release_dir.mkdir(parents=True)
    shards_dir = release_dir / "shards"
    shards_dir.mkdir()
    for index in range(shard_count):
        source = staging / f"shard-{index:03d}" / base.release_name
        destination = shards_dir / f"shard-{index:03d}"
        source.rename(destination)
        (staging / f"shard-{index:03d}").rmdir()
    staging.rmdir()

    manifest = _aggregate_manifest(base, release_dir, results, shard_count, minimum_bytes)
    (release_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if manifest["total_size_bytes"] < minimum_bytes:
        raise ValueError(f"large release is {manifest['total_size_bytes']} bytes, below required {minimum_bytes} bytes")
    summary = {
        "status": "PASS",
        "release_dir": str(release_dir.resolve()),
        "shard_count": shard_count,
        "parallel_workers": workers,
        "total_size_bytes": manifest["total_size_bytes"],
        "table_counts": manifest["table_counts"],
        "logical_dataset_sha256": manifest["logical_dataset_sha256"],
        "quality_checks": manifest["quality_checks"],
    }
    return release_dir, summary


def validate_large_release(
    release_dir: str | Path,
    config_path: str | Path = "abm/configs/large.yaml",
    *,
    workers: int | None = None,
) -> dict[str, Any]:
    root = Path(release_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    base = SimulationConfig.load(config_path)
    shard_entries = manifest["shards"]
    validation_workers = workers or min(6, len(shard_entries))
    results: dict[int, dict[str, Any]] = {}
    with ProcessPoolExecutor(max_workers=validation_workers) as executor:
        futures = {
            executor.submit(
                _validate_one_shard,
                root / entry["path"],
                base,
                int(entry["shard_index"]),
                entry["manifest_sha256"],
            ): int(entry["shard_index"])
            for entry in shard_entries
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    total_size = sum(result["size_bytes"] for result in results.values())
    counts: Counter[str] = Counter()
    for result in results.values():
        counts.update(result["table_counts"])
    if total_size != manifest["total_size_bytes"]:
        raise ValueError(f"aggregate size mismatch: manifest={manifest['total_size_bytes']} actual={total_size}")
    if dict(counts) != manifest["table_counts"]:
        raise ValueError("aggregate table counts do not match shard validation")
    if total_size < manifest["minimum_release_bytes"]:
        raise ValueError("release no longer meets its minimum byte gate")
    return {
        "status": "PASS",
        "release_dir": str(root.resolve()),
        "shards_validated": len(results),
        "total_size_bytes": total_size,
        "table_counts": dict(counts),
        "quality_checks": {
            "passed": sum(result["checks_passed"] for result in results.values()),
            "failed": 0,
        },
    }


def _build_one_shard(base: SimulationConfig, shard_root: Path, index: int) -> dict[str, Any]:
    config = replace(
        base,
        simulation_seed=base.simulation_seed + index * 1009,
        id_namespace=f"S{index:03d}",
    )
    shard_root.mkdir(parents=True, exist_ok=True)
    config_path = shard_root / "config.yaml"
    config_payload = config.canonical_dict()
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
    release_dir, summary = build_release(config_path, shard_root)
    config_path.unlink()
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    size_bytes = sum(entry["bytes"] for entry in manifest["files"]) + manifest_path.stat().st_size
    return {
        "shard_index": index,
        "logical_world_sha256": summary["logical_world_sha256"],
        "manifest_sha256": _sha256_file(manifest_path),
        "size_bytes": size_bytes,
        "table_counts": summary["table_counts"],
        "scenario_counts": manifest["scenario_counts"],
        "hard_negative_counts": manifest["hard_negative_counts"],
        "checks_passed": summary["quality_checks"]["passed"],
    }


def _validate_one_shard(
    shard_dir: Path,
    base: SimulationConfig,
    index: int,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    manifest_path = shard_dir / "manifest.json"
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        raise ValueError(f"shard-{index:03d} manifest checksum mismatch")
    manifest_check = verify_manifest(shard_dir)
    config = replace(
        base,
        simulation_seed=base.simulation_seed + index * 1009,
        id_namespace=f"S{index:03d}",
    )
    world = load_release(shard_dir)
    quality = validate_world(world, config, ParameterRegistry())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    size_bytes = sum(entry["bytes"] for entry in manifest["files"]) + manifest_path.stat().st_size
    return {
        "shard_index": index,
        "manifest_files": manifest_check["verified_file_count"],
        "checks_passed": quality["passed"],
        "size_bytes": size_bytes,
        "table_counts": world.table_counts(),
    }


def _existing_shard_result(shard_dir: Path, index: int) -> dict[str, Any]:
    manifest_path = shard_dir / "manifest.json"
    verify_manifest(shard_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quality = json.loads((shard_dir / "reports" / "quality_report.json").read_text(encoding="utf-8"))
    if quality["status"] != "PASS" or quality["failed"] != 0:
        raise ValueError(f"existing shard-{index:03d} did not pass quality gates")
    size_bytes = sum(entry["bytes"] for entry in manifest["files"]) + manifest_path.stat().st_size
    return {
        "shard_index": index,
        "logical_world_sha256": manifest["logical_world_sha256"],
        "manifest_sha256": _sha256_file(manifest_path),
        "size_bytes": size_bytes,
        "table_counts": manifest["table_counts"],
        "scenario_counts": manifest["scenario_counts"],
        "hard_negative_counts": manifest["hard_negative_counts"],
        "checks_passed": quality["passed"],
    }


def _aggregate_manifest(
    base: SimulationConfig,
    release_dir: Path,
    results: dict[int, dict[str, Any]],
    shard_count: int,
    minimum_bytes: int,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    hard_negative_counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    shards: list[dict[str, Any]] = []
    for index in range(shard_count):
        result = results[index]
        counts.update(result["table_counts"])
        scenario_counts.update(result["scenario_counts"])
        hard_negative_counts.update(result["hard_negative_counts"])
        digest.update(result["logical_world_sha256"].encode())
        shards.append(
            {
                "shard_index": index,
                "path": f"shards/shard-{index:03d}",
                "simulation_seed": base.simulation_seed + index * 1009,
                "id_namespace": f"S{index:03d}",
                "size_bytes": result["size_bytes"],
                "manifest_sha256": result["manifest_sha256"],
                "logical_world_sha256": result["logical_world_sha256"],
            }
        )
    total_size = sum(item["size_bytes"] for item in shards)
    return {
        "dataset_id": base.dataset_id,
        "dataset_version": base.dataset_version,
        "schema_version": base.schema_version,
        "release_name": base.release_name,
        "created_at": datetime.now().astimezone().isoformat(),
        "release_owner": base.release_owner,
        "simulation_start": base.simulation_start.isoformat(),
        "simulation_end": base.simulation_end.isoformat(),
        "base_simulation_seed": base.simulation_seed,
        "shard_count": shard_count,
        "minimum_release_bytes": minimum_bytes,
        "total_size_bytes": total_size,
        "logical_dataset_sha256": digest.hexdigest(),
        "table_counts": dict(counts),
        "scenario_counts": dict(scenario_counts),
        "hard_negative_counts": dict(hard_negative_counts),
        "quality_checks": {
            "passed": sum(result["checks_passed"] for result in results.values()),
            "failed": 0,
        },
        "shards": shards,
        "layout": "Each shard is an independently validated canonical release; consumers glob shards/*/bank_view/*.parquet.",
        "limitations": [
            "Shard scenario quotas are benchmark coverage and not real AML prevalence.",
            "The release is synthetic and must not be used for customer or enforcement decisions.",
            "Hidden and ground-truth directories must remain inaccessible to feature generation.",
        ],
    }


def _clear_exact_directory(path: Path, parent: Path, expected_name: str) -> None:
    resolved = path.resolve()
    if resolved.parent != parent.resolve() or resolved.name != expected_name:
        raise ValueError(f"refusing to clear unexpected path: {resolved}")
    shutil.rmtree(resolved)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
