"""FIN-07 Task 2 schema contracts: mapping rules, instances, enums, canonicalize."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

FIN07_TYPOLOGIES: frozenset[str] = frozenset(
    {f"T{str(i).zfill(2)}" for i in range(1, 11)}
)

# Synonyms after basic normalize → canonical IBM BEGIN token
PATTERN_TYPE_ALIASES: dict[str, str] = {
    "FANOUT": "FAN-OUT",
    "FAN-OUT": "FAN-OUT",
    "FAN-OUT-": "FAN-OUT",
    "FANIN": "FAN-IN",
    "FAN-IN": "FAN-IN",
    "GATHERSCATTER": "GATHER-SCATTER",
    "GATHER-SCATTER": "GATHER-SCATTER",
    "SCATTERGATHER": "SCATTER-GATHER",
    "SCATTER-GATHER": "SCATTER-GATHER",
    "CYCLE": "CYCLE",
    "STACK": "STACK",
    "BIPARTITE": "BIPARTITE",
    "RANDOM": "RANDOM",
}


class MappingStatus(str, Enum):  # noqa: UP042 — Python 3.10
    MAPPED = "MAPPED"
    PARTIAL = "PARTIAL"
    UNMAPPED = "UNMAPPED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ParseStatus(str, Enum):  # noqa: UP042
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


class SchemaValidationError(ValueError):
    pass


def canonicalize_pattern_type(raw_name: str) -> str:
    """Normalize raw BEGIN token to canonical join key (e.g. FAN OUT → FAN-OUT)."""
    value = raw_name.strip().upper()
    value = value.replace("_", "-")
    value = "-".join(value.split())
    # collapse duplicate dashes
    while "--" in value:
        value = value.replace("--", "-")
    value = value.strip("-")
    return PATTERN_TYPE_ALIASES.get(value, value)


def is_valid_typology(code: str | None) -> bool:
    if code is None:
        return True
    return code in FIN07_TYPOLOGIES


@dataclass
class TypologyMappingRule:
    ibm_pattern_type: str
    display_name: str
    mapping_status: MappingStatus
    mapping_reason: str
    mapping_version: str
    primary_typology: str | None = None
    secondary_typologies: list[str] = field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    def validate(self) -> None:
        errors: list[str] = []
        if not self.ibm_pattern_type.strip():
            errors.append("ibm_pattern_type must be non-empty")
        if self.ibm_pattern_type != canonicalize_pattern_type(self.ibm_pattern_type):
            errors.append(
                f"ibm_pattern_type must be canonical "
                f"(got {self.ibm_pattern_type!r}, "
                f"expected {canonicalize_pattern_type(self.ibm_pattern_type)!r})"
            )
        if not (self.mapping_reason and self.mapping_reason.strip()):
            errors.append("mapping_reason must be non-empty for every status")
        if not is_valid_typology(self.primary_typology):
            errors.append(f"invalid primary_typology: {self.primary_typology!r}")
        for t in self.secondary_typologies:
            if t not in FIN07_TYPOLOGIES:
                errors.append(f"invalid secondary typology: {t!r}")
        if (
            self.primary_typology is not None
            and self.primary_typology in self.secondary_typologies
        ):
            errors.append("primary_typology must not appear in secondary_typologies")
        if self.mapping_status == MappingStatus.MAPPED and self.primary_typology is None:
            errors.append("MAPPED requires primary_typology")
        if errors:
            raise SchemaValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mapping_status"] = self.mapping_status.value
        if self.reviewed_at is not None:
            d["reviewed_at"] = self.reviewed_at.isoformat()
        return d


@dataclass
class IbmPatternInstance:
    instance_id: str
    raw_pattern_name: str
    pattern_type: str
    source_record_index: int  # 0-based
    parse_status: ParseStatus
    source_file: str
    source_checksum: str
    source_start_line: int | None = None  # 1-based (editor lines)
    source_end_line: int | None = None
    referenced_accounts: list[Any] | None = None
    referenced_transactions: list[Any] | None = None
    parse_notes: str | None = None

    def validate(self) -> None:
        errors: list[str] = []
        if not self.instance_id.strip():
            errors.append("instance_id must be non-empty")
        if self.source_record_index < 0:
            errors.append("source_record_index must be 0-based (>= 0)")
        if self.pattern_type != canonicalize_pattern_type(self.pattern_type):
            errors.append(
                f"pattern_type must be canonical (got {self.pattern_type!r})"
            )
        if self.source_start_line is not None and self.source_start_line < 1:
            errors.append("source_start_line must be 1-based when set")
        if self.source_end_line is not None and self.source_end_line < 1:
            errors.append("source_end_line must be 1-based when set")
        if (
            self.source_start_line is not None
            and self.source_end_line is not None
            and self.source_end_line < self.source_start_line
        ):
            errors.append("source_end_line must be >= source_start_line")
        if not self.source_file.strip():
            errors.append("source_file must be non-empty")
        if not self.source_checksum.strip():
            errors.append("source_checksum must be non-empty")
        if errors:
            raise SchemaValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["parse_status"] = self.parse_status.value
        return d


@dataclass
class MappingCatalogSource:
    file: str
    sha256: str
    parser_version: str


@dataclass
class MappingCatalog:
    """Envelope: mapping_version + source metadata + rules list."""

    mapping_version: str
    source: MappingCatalogSource
    rules: list[TypologyMappingRule] = field(default_factory=list)

    def validate(self) -> None:
        if not self.mapping_version.strip():
            raise SchemaValidationError("mapping_version must be non-empty")
        if not self.source.file.strip() or not self.source.sha256.strip():
            raise SchemaValidationError("source.file and source.sha256 required")
        seen: set[str] = set()
        for rule in self.rules:
            rule.validate()
            if rule.mapping_version != self.mapping_version:
                raise SchemaValidationError(
                    f"rule {rule.ibm_pattern_type} mapping_version "
                    f"!= catalog {self.mapping_version}"
                )
            if rule.ibm_pattern_type in seen:
                raise SchemaValidationError(
                    f"duplicate ibm_pattern_type in version: {rule.ibm_pattern_type}"
                )
            seen.add(rule.ibm_pattern_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_version": self.mapping_version,
            "source": asdict(self.source),
            "rules": [r.to_dict() for r in self.rules],
        }


def load_catalog_from_json(path: str | Path) -> MappingCatalog:
    """Load and validate a mapping catalog JSON file."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    source = MappingCatalogSource(
        file=data["source"]["file"],
        sha256=data["source"]["sha256"],
        parser_version=data["source"]["parser_version"],
    )
    rules: list[TypologyMappingRule] = []
    for r in data["rules"]:
        reviewed_at = r.get("reviewed_at")
        if isinstance(reviewed_at, str) and reviewed_at:
            reviewed_at = datetime.fromisoformat(reviewed_at)
        else:
            reviewed_at = None
        rules.append(
            TypologyMappingRule(
                ibm_pattern_type=r["ibm_pattern_type"],
                display_name=r["display_name"],
                mapping_status=MappingStatus(r["mapping_status"]),
                mapping_reason=r["mapping_reason"],
                mapping_version=r["mapping_version"],
                primary_typology=r.get("primary_typology"),
                secondary_typologies=list(r.get("secondary_typologies") or []),
                reviewed_by=r.get("reviewed_by"),
                reviewed_at=reviewed_at,
            )
        )
    catalog = MappingCatalog(
        mapping_version=data["mapping_version"],
        source=source,
        rules=rules,
    )
    catalog.validate()
    return catalog
