"""High-level build and validation workflow for ABM-BANK releases."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from abm.exporters.release import ReleaseExporter
from abm.generator import AbmBankGenerator
from abm.registry import ParameterRegistry, SimulationConfig
from abm.validation.release import validate_world


def build_release(
    config_path: str | Path,
    output_root: str | Path = "artifacts",
    *,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    config = SimulationConfig.load(config_path)
    registry = ParameterRegistry()
    if registry.version != config.parameter_registry_version:
        raise ValueError(
            f"config expects parameter registry {config.parameter_registry_version}, found {registry.version}"
        )
    world = AbmBankGenerator(config, registry).generate()
    quality = validate_world(world, config, registry)
    statistical = _statistical_summary(world, quality)
    reports = {
        "quality_report": quality,
        "behavioral_suitability_report": quality["behavioral_summary"],
        "graph_suitability_report": quality["graph_summary"],
        "statistical_summary": statistical,
    }
    exporter = ReleaseExporter(config, registry, output_root)
    release_dir = exporter.write(world, reports, overwrite=overwrite)
    result = {
        "status": "PASS",
        "release_dir": str(release_dir.resolve()),
        "table_counts": world.table_counts(),
        "logical_world_sha256": world.logical_fingerprint(),
        "quality_checks": {"passed": quality["passed"], "failed": quality["failed"]},
    }
    return release_dir, result


def _statistical_summary(world: Any, quality: dict[str, Any]) -> dict[str, Any]:
    def distribution(rows: list[dict[str, Any]], column: str) -> dict[str, Any]:
        counts = Counter(str(row[column]) for row in rows)
        total = sum(counts.values())
        return {key: {"count": count, "share": count / total} for key, count in sorted(counts.items())}

    calibration = next(check["details"] for check in quality["checks"] if check["name"] == "statistical_calibration")
    return {
        "customer_type": distribution(world.customers, "customer_type"),
        "customer_segment": distribution(world.customers, "segment"),
        "customer_region": distribution(world.customers, "region_code"),
        "account_product": distribution(world.accounts, "product_type"),
        "merchant_category": distribution(world.merchants, "merchant_category_code"),
        "transaction_type": distribution(world.transactions, "transaction_type"),
        "channel": distribution(world.transactions, "channel"),
        "dataset_split": distribution(world.transactions, "dataset_split"),
        "calibration": calibration,
        "interpretation": "Synthetic realized marginals for reproducibility checks; not claims about a real bank portfolio.",
    }
