#!/usr/bin/env python3
"""Canonical graph runner with process-isolated detector phases."""

from __future__ import annotations

import hashlib
import json
import resource
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.graph_artifact_validator import validate_graph_artifacts  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_phase(phase: str, *, db: Path, features: Path, cutoffs: Path, config: Path, out_dir: Path) -> dict:
    det = out_dir / f"{phase}_detection.parquet"
    ev = out_dir / f"{phase}_evidence.jsonl"
    cmd = [
        sys.executable,
        str(ROOT / "scripts/run_graph_phase.py"),
        phase,
        "--db",
        str(db),
        "--features",
        str(features),
        "--cutoffs",
        str(cutoffs),
        "--config",
        str(config),
        "--detection-out",
        str(det),
        "--evidence-out",
        str(ev),
    ]
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"{phase} phase failed:\n{proc.stdout}\n{proc.stderr}")
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    result["orchestration_runtime_s"] = round(time.perf_counter() - started, 3)
    result["detection_path"] = str(det)
    result["evidence_path"] = str(ev)
    return result


def merge_artifacts(
    phase_results: list[dict], detection_path: Path, evidence_path: Path
) -> tuple[int, int, dict[str, int], dict[str, list[str]]]:
    frames = []
    pattern_counts: dict[str, int] = {}
    detector_versions: dict[str, set[str]] = {}
    for item in phase_results:
        frame = pd.read_parquet(item["detection_path"])
        frames.append(frame)
        for pattern, count in frame["detected_pattern"].value_counts().to_dict().items():
            pattern_counts[str(pattern)] = pattern_counts.get(str(pattern), 0) + int(count)
        for pattern, versions in frame.groupby("detected_pattern")["detector_version"]:
            detector_versions.setdefault(str(pattern), set()).update(str(v) for v in versions.dropna().unique())
    detections = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not detections.empty:
        detections = detections.sort_values(["as_of_ts", "detected_pattern", "account_key"], kind="mergesort")
    detection_path.parent.mkdir(parents=True, exist_ok=True)
    detections.to_parquet(detection_path, index=False)
    evidence_rows = 0
    with evidence_path.open("w", encoding="utf-8") as dst:
        for item in phase_results:
            with Path(item["evidence_path"]).open(encoding="utf-8") as src:
                for line in src:
                    if line.strip():
                        dst.write(line)
                        evidence_rows += 1
    return len(detections), evidence_rows, pattern_counts, {k: sorted(v) for k, v in detector_versions.items()}


def main() -> int:
    db = ROOT / "data/processed/aml.duckdb"
    features = ROOT / "data/processed/graph_features_v1.parquet"
    cutoffs = ROOT / "data/processed/split_cutoffs.json"
    configs = {
        "fan": ROOT / "configs/graph/graph_fan_config_v3.json",
        "gather": ROOT / "configs/graph/graph_gather_config_v1.json",
        "cycle": ROOT / "configs/graph/graph_cycle_config_v1.json",
    }
    # CYCLE has no separate config; record the detector source/version instead.
    configs["cycle"] = ROOT / "src/data/cycle_detector.py"
    detection_path = ROOT / "data/processed/graph_detection_v1.parquet"
    evidence_path = ROOT / "data/processed/graph_evidence_v1.jsonl"
    manifest_path = ROOT / "reports/graph_pipeline_manifest_v1.json"
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="graph_phases_", dir="/tmp") as temp:
        out_dir = Path(temp)
        phase_results = [
            run_phase(p, db=db, features=features, cutoffs=cutoffs, config=configs[p], out_dir=out_dir)
            for p in ("fan", "gather", "cycle")
        ]
        merge_t0 = time.perf_counter()
        det_rows, ev_rows, counts, detector_versions = merge_artifacts(phase_results, detection_path, evidence_path)
        merge_runtime = round(time.perf_counter() - merge_t0, 3)
    validation_t0 = time.perf_counter()
    validation = validate_graph_artifacts(detection_path, evidence_path, db_path=db)
    validation_runtime = round(time.perf_counter() - validation_t0, 3)
    manifest = {
        "manifest_version": "graph_pipeline_manifest_v2",
        "input_db_checksum": sha256(db),
        "feature_artifact_checksum": sha256(features),
        "feature_schema_version": "graph_features_v1",
        "detector_versions": detector_versions,
        "config_hashes": {str(p.relative_to(ROOT)): sha256(p) for p in configs.values()},
        "snapshot_range": {
            "min": str(pd.to_datetime(pd.read_parquet(detection_path).snapshot_date).min().date()),
            "max": str(pd.to_datetime(pd.read_parquet(detection_path).snapshot_date).max().date()),
        },
        "row_counts": {"detections": det_rows, "evidence": ev_rows, "by_pattern": counts},
        "validation": validation,
        "telemetry": {
            "phases": phase_results,
            "merge_runtime_s": merge_runtime,
            "validation_runtime_s": validation_runtime,
            "parent_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "peak_phase_rss_mb": max(r["peak_rss_mb"] for r in phase_results),
        },
        "runtime_s": round(time.perf_counter() - t0, 3),
        "created_at": datetime.now(UTC).isoformat(),
        "test_status": "PASS" if validation["status"] == "PASS" else "FAIL",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if validation["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
