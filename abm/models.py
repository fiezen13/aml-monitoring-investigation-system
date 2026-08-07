"""In-memory release model for ABM-BANK.

The MVP intentionally keeps bounded master and event tables in memory. At the
10,000-customer release size this remains well below development-machine memory,
while Parquet writing is still performed one table/partition at a time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MONEY_QUANTUM = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    """Return an exact, non-negative two-decimal monetary value."""
    result = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if result < 0:
        raise ValueError(f"money must be non-negative, received {result}")
    return result


@dataclass
class ReleaseWorld:
    """All tables that make up one canonical ABM-BANK release."""

    customers: list[dict[str, Any]] = field(default_factory=list)
    businesses: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    devices: list[dict[str, Any]] = field(default_factory=list)
    merchants: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    balance_snapshots: list[dict[str, Any]] = field(default_factory=list)

    entity_labels: list[dict[str, Any]] = field(default_factory=list)
    transaction_labels: list[dict[str, Any]] = field(default_factory=list)
    scenario_instances: list[dict[str, Any]] = field(default_factory=list)
    networks: list[dict[str, Any]] = field(default_factory=list)
    network_members: list[dict[str, Any]] = field(default_factory=list)
    hard_negative_instances: list[dict[str, Any]] = field(default_factory=list)
    split_assignments: list[dict[str, Any]] = field(default_factory=list)

    hidden_actions: list[dict[str, Any]] = field(default_factory=list)
    hidden_relationships: list[dict[str, Any]] = field(default_factory=list)

    def table_counts(self) -> dict[str, int]:
        return {name: len(value) for name, value in self.__dict__.items() if isinstance(value, list)}

    def logical_fingerprint(self) -> str:
        """Stable logical hash independent of Parquet writer metadata."""

        digest = hashlib.sha256()
        for table_name in sorted(self.__dict__):
            rows = getattr(self, table_name)
            if not isinstance(rows, list):
                continue
            digest.update(table_name.encode("utf-8"))
            for row in rows:
                normalized = {key: _json_value(value) for key, value in sorted(row.items())}
                digest.update(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    return value
