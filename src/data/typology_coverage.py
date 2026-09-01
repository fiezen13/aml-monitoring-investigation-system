"""Build FIN-07 T01–T10 typology coverage from instances + mapping catalog."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.data.typology_schema import (
    FIN07_TYPOLOGIES,
    IbmPatternInstance,
    MappingCatalog,
    MappingStatus,
    TypologyMappingRule,
)

TYPOLOGY_NAMES: dict[str, str] = {
    "T01": "Structuring / Smurfing",
    "T02": "Money mule network",
    "T03": "Circular / Round-tripping",
    "T04": "Fan-in / Fan-out",
    "T05": "Rapid pass-through",
    "T06": "Crypto-related laundering",
    "T07": "Online gambling laundering",
    "T08": "Trade-based ML (TBML)",
    "T09": "PEP / high-risk customer screening",
    "T10": "Profile mismatch",
}

DEFAULT_MISSING_NOTES: dict[str, str] = {
    "T06": "Không có pattern IBM LI-Small map tới T06; không cam kết đánh giá từ dataset này trừ khi bổ sung ca tự sinh.",
    "T07": "Không có pattern IBM LI-Small map tới T07.",
    "T08": "Không có pattern IBM LI-Small map tới T08.",
    "T09": "Không có trong IBM; ground truth screening thuộc Sprint 2.",
    "T10": "Không có trong IBM; nhãn T10 sinh ở Task 3 (tiêm lệch hồ sơ).",
}


def _typologies_touched_by_rule(rule: TypologyMappingRule) -> set[str]:
    """Typologies this rule contributes to coverage (MAPPED/PARTIAL only)."""
    if rule.mapping_status in (MappingStatus.UNMAPPED, MappingStatus.OUT_OF_SCOPE):
        return set()
    touched: set[str] = set(rule.secondary_typologies)
    if rule.primary_typology:
        touched.add(rule.primary_typology)
    return touched


def build_coverage(
    instances: list[IbmPatternInstance],
    catalog: MappingCatalog,
) -> dict[str, Any]:
    rules_by_type = {r.ibm_pattern_type: r for r in catalog.rules}
    instance_counts: dict[str, int] = defaultdict(int)
    for inst in instances:
        instance_counts[inst.pattern_type] += 1

    # typology -> set of ibm types that touch it
    types_for_typo: dict[str, set[str]] = {t: set() for t in sorted(FIN07_TYPOLOGIES)}
    for rule in catalog.rules:
        for typo in _typologies_touched_by_rule(rule):
            types_for_typo[typo].add(rule.ibm_pattern_type)

    rows: list[dict[str, Any]] = []
    covered_n = 0
    for code in sorted(FIN07_TYPOLOGIES):
        ibm_types = sorted(types_for_typo[code])
        inst_count = sum(instance_counts[t] for t in ibm_types)
        covered = len(ibm_types) > 0
        if covered:
            covered_n += 1
        notes_parts: list[str] = []
        for t in ibm_types:
            rule = rules_by_type[t]
            notes_parts.append(f"{t}:{rule.mapping_status.value}")
        notes = "; ".join(notes_parts) if notes_parts else DEFAULT_MISSING_NOTES.get(code, "")
        rows.append(
            {
                "fin07_typology": code,
                "typology_name": TYPOLOGY_NAMES.get(code, code),
                "covered": covered,
                "ibm_pattern_types": ibm_types,
                "pattern_instance_count": inst_count,
                "notes": notes,
            }
        )

    unmapped_types = [t for t, c in instance_counts.items() if t not in rules_by_type]
    return {
        "mapping_version": catalog.mapping_version,
        "n_instances": len(instances),
        "n_pattern_types_in_file": len(instance_counts),
        "type_coverage": covered_n / 10.0,
        "covered_typology_count": covered_n,
        "instance_counts_by_pattern_type": dict(sorted(instance_counts.items())),
        "unmapped_pattern_types_in_file": unmapped_types,
        "rows": rows,
    }


def coverage_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Typology coverage — FIN-07 Task 2",
        "",
        f"- mapping_version: `{report['mapping_version']}`",
        f"- instances: {report['n_instances']}",
        f"- type_coverage: **{report['covered_typology_count']}/10** ({report['type_coverage']:.0%})",
        "",
        "| Typology | Name | Covered | IBM types | Instance count | Notes |",
        "|----------|------|---------|-----------|----------------|-------|",
    ]
    for row in report["rows"]:
        ibm = ", ".join(row["ibm_pattern_types"]) or "—"
        notes = (row["notes"] or "").replace("|", "\\|")
        lines.append(
            f"| {row['fin07_typology']} | {row['typology_name']} | "
            f"{row['covered']} | {ibm} | {row['pattern_instance_count']} | {notes} |"
        )
    lines.append("")
    return "\n".join(lines)
