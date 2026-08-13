"""Tests for Task 2 typology schema contracts."""

from __future__ import annotations

import pytest

from src.data.typology_schema import (
    IbmPatternInstance,
    MappingCatalog,
    MappingCatalogSource,
    MappingStatus,
    ParseStatus,
    SchemaValidationError,
    TypologyMappingRule,
    canonicalize_pattern_type,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CYCLE", "CYCLE"),
        ("cycle", "CYCLE"),
        ("FAN-IN", "FAN-IN"),
        ("FAN IN", "FAN-IN"),
        ("FanOut", "FAN-OUT"),
        ("FANOUT", "FAN-OUT"),
        ("gather_scatter", "GATHER-SCATTER"),
        ("SCATTER GATHER", "SCATTER-GATHER"),
    ],
)
def test_canonicalize_pattern_type(raw: str, expected: str) -> None:
    assert canonicalize_pattern_type(raw) == expected


def test_mapped_requires_reason_and_primary() -> None:
    rule = TypologyMappingRule(
        ibm_pattern_type="CYCLE",
        display_name="Cycle",
        mapping_status=MappingStatus.MAPPED,
        mapping_reason="",
        mapping_version="v1.0",
        primary_typology="T03",
    )
    with pytest.raises(SchemaValidationError, match="mapping_reason"):
        rule.validate()

    rule.mapping_reason = "Chuỗi hop khép kín, khớp T03."
    rule.primary_typology = None
    with pytest.raises(SchemaValidationError, match="MAPPED requires primary"):
        rule.validate()


def test_mapped_ok() -> None:
    rule = TypologyMappingRule(
        ibm_pattern_type="CYCLE",
        display_name="Cycle",
        mapping_status=MappingStatus.MAPPED,
        mapping_reason="Chuỗi chuyển tiền tạo đường đi khép kín, phù hợp T03.",
        mapping_version="v1.0",
        primary_typology="T03",
        secondary_typologies=[],
    )
    rule.validate()


def test_partial_allows_null_primary() -> None:
    rule = TypologyMappingRule(
        ibm_pattern_type="GATHER-SCATTER",
        display_name="Gather-Scatter",
        mapping_status=MappingStatus.PARTIAL,
        mapping_reason="Overlap T02/T04, chưa chốt primary.",
        mapping_version="v1.0",
        primary_typology=None,
        secondary_typologies=["T02", "T04"],
    )
    rule.validate()


def test_primary_not_in_secondary() -> None:
    rule = TypologyMappingRule(
        ibm_pattern_type="FAN-IN",
        display_name="Fan-In",
        mapping_status=MappingStatus.PARTIAL,
        mapping_reason="Primary T04 nhưng ghi nhầm secondary.",
        mapping_version="v1.0",
        primary_typology="T04",
        secondary_typologies=["T04", "T02"],
    )
    with pytest.raises(SchemaValidationError, match="secondary"):
        rule.validate()


def test_catalog_unique_types_and_envelope() -> None:
    catalog = MappingCatalog(
        mapping_version="v1.0",
        source=MappingCatalogSource(
            file="data/raw/ibm-aml/LI-Small_Patterns.txt",
            sha256="abc",
            parser_version="v1.0",
        ),
        rules=[
            TypologyMappingRule(
                ibm_pattern_type="CYCLE",
                display_name="Cycle",
                mapping_status=MappingStatus.MAPPED,
                mapping_reason="Khớp T03.",
                mapping_version="v1.0",
                primary_typology="T03",
            ),
            TypologyMappingRule(
                ibm_pattern_type="CYCLE",
                display_name="Cycle dup",
                mapping_status=MappingStatus.UNMAPPED,
                mapping_reason="Trùng type.",
                mapping_version="v1.0",
            ),
        ],
    )
    with pytest.raises(SchemaValidationError, match="duplicate"):
        catalog.validate()


def test_instance_index_and_lines() -> None:
    inst = IbmPatternInstance(
        instance_id="inst-0",
        raw_pattern_name="FAN-IN",
        pattern_type="FAN-IN",
        source_record_index=0,
        parse_status=ParseStatus.OK,
        source_file="data/raw/ibm-aml/LI-Small_Patterns.txt",
        source_checksum="abc",
        source_start_line=1,
        source_end_line=5,
    )
    inst.validate()

    bad = IbmPatternInstance(
        instance_id="x",
        raw_pattern_name="FAN-IN",
        pattern_type="FAN-IN",
        source_record_index=-1,
        parse_status=ParseStatus.OK,
        source_file="f",
        source_checksum="c",
    )
    with pytest.raises(SchemaValidationError, match="0-based"):
        bad.validate()
