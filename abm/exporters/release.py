"""Write a complete, reproducible ABM-BANK release to Parquet."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from abm.models import ReleaseWorld
from abm.registry import ParameterRegistry, SimulationConfig

BANK_TABLES = {
    "customers": "customers.parquet",
    "businesses": "businesses.parquet",
    "accounts": "accounts.parquet",
    "devices": "devices.parquet",
    "merchants": "merchants.parquet",
    "relationships": "relationships.parquet",
    "sessions": "device_sessions.parquet",
    "balance_snapshots": "balance_snapshots.parquet",
}
GROUND_TRUTH_TABLES = {
    "entity_labels": "entity_labels.parquet",
    "transaction_labels": "transaction_labels.parquet",
    "scenario_instances": "scenario_instances.parquet",
    "networks": "networks.parquet",
    "network_members": "network_members.parquet",
    "hard_negative_instances": "hard_negative_instances.parquet",
    "split_assignments": "split_assignments.parquet",
}
HIDDEN_TABLES = {
    "hidden_actions": "hidden_actions.parquet",
    "hidden_relationships": "hidden_relationships.parquet",
}

UTC_TIMESTAMP_COLUMNS = {
    "event_time",
    "posting_time",
    "available_from",
    "created_at",
    "valid_from",
    "valid_to",
    "customer_since",
    "opened_at",
    "closed_at",
    "first_seen_at",
    "last_seen_at",
    "established_at",
    "known_from",
    "snapshot_time",
    "active_from",
    "active_to",
    "causal_start_time",
    "causal_end_time",
}
MONEY_COLUMNS = {
    "amount",
    "balance",
    "opening_balance",
    "monthly_scale_vnd",
    "expected_monthly_turnover_vnd",
    "monthly_turnover_vnd",
}
LIST_COLUMNS = {
    "owner_customer_ids",
    "quality_flags",
    "entity_ids",
    "transaction_ids",
    "true_actor_ids",
    "target_entity_ids",
}


class ReleaseExporter:
    """Materialize Bank View, ground truth, hidden state, and release metadata."""

    def __init__(
        self,
        config: SimulationConfig,
        registry: ParameterRegistry,
        output_root: str | Path = "artifacts",
    ) -> None:
        self.config = config
        self.registry = registry
        self.output_root = Path(output_root)
        self.release_dir = self.output_root / config.release_name

    def write(
        self,
        world: ReleaseWorld,
        reports: dict[str, Any] | None = None,
        *,
        overwrite: bool = False,
    ) -> Path:
        if self.release_dir.exists() and any(self.release_dir.iterdir()):
            if not overwrite:
                raise FileExistsError(
                    f"release already exists: {self.release_dir}; pass overwrite=True to replace files"
                )
            self._clear_generated_release()
        self.release_dir.mkdir(parents=True, exist_ok=True)
        for child in ("bank_view", "ground_truth", "hidden", "reports", "metadata"):
            (self.release_dir / child).mkdir(exist_ok=True)

        for table_name, filename in BANK_TABLES.items():
            self._write_rows(getattr(world, table_name), self.release_dir / "bank_view" / filename)
        self._write_partitioned_transactions(world.transactions)
        for table_name, filename in GROUND_TRUTH_TABLES.items():
            self._write_rows(getattr(world, table_name), self.release_dir / "ground_truth" / filename)
        for table_name, filename in HIDDEN_TABLES.items():
            self._write_rows(getattr(world, table_name), self.release_dir / "hidden" / filename)

        self._write_json(self.release_dir / "metadata" / "config.json", self.config.canonical_dict())
        self._write_json(
            self.release_dir / "metadata" / "parameter_registry.json",
            {key: value for key, value in sorted(self.registry.cards.items())},
        )
        self._write_json(
            self.release_dir / "metadata" / "source_registry.json",
            {key: value for key, value in sorted(self.registry.sources.items())},
        )
        for name, report in sorted((reports or {}).items()):
            self._write_json(self.release_dir / "reports" / f"{name}.json", report)

        manifest = self._manifest(world)
        self._write_json(self.release_dir / "manifest.json", manifest)
        return self.release_dir

    def refresh_manifest(self, world: ReleaseWorld) -> None:
        self._write_json(self.release_dir / "manifest.json", self._manifest(world))

    def _clear_generated_release(self) -> None:
        """Remove only files below the exact versioned release selected by --overwrite."""
        resolved_release = self.release_dir.resolve()
        resolved_root = self.output_root.resolve()
        if resolved_release.parent != resolved_root or resolved_release.name != self.config.release_name:
            raise ValueError(f"refusing to clear unexpected release path: {resolved_release}")
        for path in sorted(resolved_release.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    def _write_partitioned_transactions(self, rows: list[dict[str, Any]]) -> None:
        destination = self.release_dir / "bank_view" / "transactions"
        destination.mkdir(exist_ok=True)
        partitions: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            event_time = row["event_time"]
            business_time = event_time.astimezone(self.config.simulation_start.tzinfo)
            if self.config.transaction_partition == "day":
                key = business_time.strftime("%Y-%m-%d")
                partition_name = "event_date"
            else:
                key = business_time.strftime("%Y-%m")
                partition_name = "event_month"
            partitions[key].append(row)
        for key, partition_rows in sorted(partitions.items()):
            partition_rows.sort(key=lambda item: (item["event_time"], item["transaction_id"]))
            self._write_rows(
                partition_rows,
                destination / f"{partition_name}={key}" / "part-00000.parquet",
            )

    def _write_rows(self, rows: list[dict[str, Any]], destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            raise ValueError(f"release table cannot be empty: {destination.name}")
        schema = _schema_for_rows(rows)
        table = pa.Table.from_pylist(rows, schema=schema)
        metadata = dict(table.schema.metadata or {})
        metadata[b"dataset_id"] = self.config.dataset_id.encode()
        metadata[b"dataset_version"] = self.config.dataset_version.encode()
        metadata[b"schema_version"] = self.config.schema_version.encode()
        table = table.replace_schema_metadata(metadata)
        pq.write_table(
            table,
            destination,
            compression=self.config.parquet_compression,
            use_dictionary=True,
            write_statistics=True,
            data_page_version="2.0",
        )

    def _manifest(self, world: ReleaseWorld) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        for path in sorted(self.release_dir.rglob("*")):
            if not path.is_file() or path.name == "manifest.json":
                continue
            files.append(
                {
                    "path": path.relative_to(self.release_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
        return {
            "dataset_id": self.config.dataset_id,
            "dataset_version": self.config.dataset_version,
            "schema_version": self.config.schema_version,
            "release_name": self.config.release_name,
            "created_at": datetime.now().astimezone().isoformat(),
            "release_owner": self.config.release_owner,
            "simulation_seed": self.config.simulation_seed,
            "simulation_start": self.config.simulation_start.isoformat(),
            "simulation_end": self.config.simulation_end.isoformat(),
            "config_sha256": self.config.fingerprint(),
            "parameter_registry_sha256": self.registry.fingerprint(),
            "parameter_registry_version": self.config.parameter_registry_version,
            "source_registry_version": self.config.source_registry_version,
            "source_ids": sorted(self.registry.sources),
            "logical_world_sha256": world.logical_fingerprint(),
            "table_counts": world.table_counts(),
            "scenario_counts": dict(sorted(_counts(world.scenario_instances, "scenario_type").items())),
            "hard_negative_counts": dict(sorted(_counts(world.hard_negative_instances, "scenario_type").items())),
            "git_commit": _git_commit(),
            "runtime": {"python": platform.python_version(), "pyarrow": pa.__version__},
            "files": files,
            "limitations": [
                "Synthetic benchmark quotas are not estimates of real AML prevalence.",
                "Public aggregate evidence constrains marginals but does not reproduce any real person.",
                "Bank View intentionally excludes hidden intent, scenario labels, and true coordination.",
                "VND values are synthetic and must not be used for credit, enforcement, or customer decisions.",
            ],
        }

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )


def _schema_for_rows(rows: list[dict[str, Any]]) -> pa.Schema:
    fields: list[pa.Field] = []
    for name in rows[0]:
        values = [row.get(name) for row in rows]
        nullable = any(value is None for value in values)
        if name in UTC_TIMESTAMP_COLUMNS:
            field_type = pa.timestamp("us", tz="UTC")
        elif name in MONEY_COLUMNS:
            field_type = pa.decimal128(20, 2)
        elif name in LIST_COLUMNS:
            field_type = pa.list_(pa.string())
        else:
            representative = next((value for value in values if value is not None), None)
            if isinstance(representative, bool):
                field_type = pa.bool_()
            elif isinstance(representative, int):
                field_type = pa.int64()
            elif isinstance(representative, float):
                field_type = pa.float64()
            elif isinstance(representative, Decimal):
                field_type = pa.decimal128(20, 2)
            elif isinstance(representative, (datetime, date)):
                field_type = pa.timestamp("us", tz="UTC")
            elif isinstance(representative, list):
                field_type = pa.list_(pa.string())
            else:
                field_type = pa.string()
        fields.append(pa.field(name, field_type, nullable=nullable))
    return pa.schema(fields)


def load_release(release_dir: str | Path) -> ReleaseWorld:
    """Load every data table from a materialized release for independent validation."""
    root = Path(release_dir)
    if not (root / "manifest.json").is_file():
        raise FileNotFoundError(f"not an ABM-BANK release: {root}")
    world = ReleaseWorld()
    for table_name, filename in BANK_TABLES.items():
        setattr(world, table_name, pq.read_table(root / "bank_view" / filename).to_pylist())
    transaction_files = sorted((root / "bank_view" / "transactions").glob("*/part-*.parquet"))
    if not transaction_files:
        raise FileNotFoundError("release has no transaction partitions")
    world.transactions = [row for path in transaction_files for row in pq.read_table(path).to_pylist()]
    for table_name, filename in GROUND_TRUTH_TABLES.items():
        setattr(world, table_name, pq.read_table(root / "ground_truth" / filename).to_pylist())
    for table_name, filename in HIDDEN_TABLES.items():
        setattr(world, table_name, pq.read_table(root / "hidden" / filename).to_pylist())
    return world


def verify_manifest(release_dir: str | Path) -> dict[str, Any]:
    """Verify all recorded files and reject unmanifested release payloads."""
    root = Path(release_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = {item["path"]: item for item in manifest["files"]}
    actual_paths = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name != "manifest.json"
    }
    missing = sorted(set(expected) - actual_paths)
    unexpected = sorted(actual_paths - set(expected))
    mismatched: list[str] = []
    for relative, entry in expected.items():
        path = root / relative
        if path.is_file() and (path.stat().st_size != entry["bytes"] or _sha256_file(path) != entry["sha256"]):
            mismatched.append(relative)
    if missing or unexpected or mismatched:
        raise ValueError(
            f"manifest verification failed: missing={missing}, unexpected={unexpected}, mismatched={mismatched}"
        )
    return {"status": "PASS", "verified_file_count": len(expected)}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(rows: list[dict[str, Any]], column: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row[column])
        result[key] = result.get(key, 0) + 1
    return result


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"cannot serialize {type(value).__name__}")
