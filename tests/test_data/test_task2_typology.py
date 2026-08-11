"""Tests for FIN-07 Task 2 pattern parse + typology coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.pattern_parser import file_sha256, parse_pattern_file
from src.data.task2_pipeline import run_task2_typology
from src.data.typology_coverage import build_coverage
from src.data.typology_schema import load_catalog_from_json

FIXTURE_PATTERNS = Path(__file__).parent / "fixtures" / "tiny_patterns.txt"
FIXTURE_CATALOG = Path(__file__).parent / "fixtures" / "tiny_catalog.json"
FULL_PATTERNS = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "ibm_li_small"
    / "LI-Small_Patterns.txt"
)
FULL_CATALOG = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reference"
    / "typology_mapping_catalog_v1.json"
)


def test_parse_tiny_patterns() -> None:
    instances, checksum = parse_pattern_file(FIXTURE_PATTERNS)
    assert len(instances) == 2
    assert checksum == file_sha256(FIXTURE_PATTERNS)
    assert instances[0].pattern_type == "FAN-IN"
    assert instances[0].source_record_index == 0
    assert instances[0].source_start_line == 1
    assert instances[0].referenced_accounts
    assert instances[1].pattern_type == "CYCLE"
    assert instances[1].source_record_index == 1


def test_catalog_and_coverage_tiny(tmp_path: Path) -> None:
    catalog = json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))
    catalog["source"]["sha256"] = file_sha256(FIXTURE_PATTERNS)
    cat_path = tmp_path / "catalog.json"
    cat_path.write_text(json.dumps(catalog), encoding="utf-8")

    loaded = load_catalog_from_json(cat_path)
    assert all(r.mapping_reason.strip() for r in loaded.rules)

    instances, _ = parse_pattern_file(FIXTURE_PATTERNS)
    types_in_file = {i.pattern_type for i in instances}
    rule_types = {r.ibm_pattern_type for r in loaded.rules}
    assert types_in_file <= rule_types

    report = build_coverage(instances, loaded)
    assert len(report["rows"]) == 10
    assert report["covered_typology_count"] == 2  # T03, T04
    by_code = {r["fin07_typology"]: r for r in report["rows"]}
    assert by_code["T03"]["covered"] is True
    assert by_code["T04"]["covered"] is True
    assert by_code["T10"]["covered"] is False


def test_pipeline_reproducible(tmp_path: Path) -> None:
    catalog = json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))
    catalog["source"]["sha256"] = file_sha256(FIXTURE_PATTERNS)
    cat_path = tmp_path / "catalog.json"
    cat_path.write_text(json.dumps(catalog), encoding="utf-8")

    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    r1 = run_task2_typology(FIXTURE_PATTERNS, cat_path, out1)
    r2 = run_task2_typology(FIXTURE_PATTERNS, cat_path, out2)
    assert r1["n_instances"] == r2["n_instances"] == 2
    a = (out1 / "ibm_pattern_instances.json").read_text(encoding="utf-8")
    b = (out2 / "ibm_pattern_instances.json").read_text(encoding="utf-8")
    assert a == b


@pytest.mark.skipif(not FULL_PATTERNS.exists(), reason="LI-Small_Patterns.txt not present")
def test_full_li_small_instance_count() -> None:
    instances, _ = parse_pattern_file(FULL_PATTERNS)
    assert len(instances) == 117
    catalog = load_catalog_from_json(FULL_CATALOG)
    assert len(catalog.rules) == 8
    report = build_coverage(instances, catalog)
    assert len(report["rows"]) == 10
    assert report["covered_typology_count"] == 5  # T01–T05
    assert report["n_instances"] == 117
