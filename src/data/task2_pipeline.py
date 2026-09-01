"""FIN-07 Task 2 pipeline: parse patterns → join catalog → coverage artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data.pattern_parser import PARSER_VERSION, parse_pattern_file
from src.data.typology_coverage import build_coverage, coverage_to_markdown
from src.data.typology_schema import load_catalog_from_json


def run_task2_typology(
    patterns_path: str | Path,
    catalog_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    patterns_path = Path(patterns_path)
    catalog_path = Path(catalog_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    instances, checksum = parse_pattern_file(
        patterns_path,
        source_file_label=str(patterns_path),
    )
    catalog = load_catalog_from_json(catalog_path)

    # Warn (do not fail) if catalog checksum differs from on-disk file — still run
    checksum_note = None
    if catalog.source.sha256 != checksum:
        checksum_note = (
            f"Catalog source.sha256 ({catalog.source.sha256[:12]}...) "
            f"!= file sha256 ({checksum[:12]}...); coverage still computed."
        )

    for inst in instances:
        inst.validate()

    coverage = build_coverage(instances, catalog)
    if checksum_note:
        coverage["checksum_warning"] = checksum_note

    # Enrich catalog copy with instance counts
    counts = coverage["instance_counts_by_pattern_type"]
    catalog_out = catalog.to_dict()
    catalog_out["source"]["sha256_runtime"] = checksum
    catalog_out["source"]["parser_version_runtime"] = PARSER_VERSION
    for rule in catalog_out["rules"]:
        rule["instance_count"] = counts.get(rule["ibm_pattern_type"], 0)

    instances_path = out_dir / "ibm_pattern_instances.json"
    catalog_out_path = out_dir / "typology_mapping_catalog.json"
    coverage_json_path = out_dir / "typology_coverage.json"
    coverage_md_path = out_dir / "typology_coverage.md"

    instances_path.write_text(
        json.dumps([i.to_dict() for i in instances], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    catalog_out_path.write_text(
        json.dumps(catalog_out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    coverage_json_path.write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    coverage_md_path.write_text(coverage_to_markdown(coverage), encoding="utf-8")

    return {
        "n_instances": len(instances),
        "checksum": checksum,
        "type_coverage": coverage["type_coverage"],
        "covered_typology_count": coverage["covered_typology_count"],
        "checksum_warning": checksum_note,
        "artifacts": {
            "instances": str(instances_path),
            "catalog": str(catalog_out_path),
            "coverage_json": str(coverage_json_path),
            "coverage_md": str(coverage_md_path),
        },
    }
