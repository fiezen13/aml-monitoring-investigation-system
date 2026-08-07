"""Parse `HI-*_Patterns.txt` into scenario instances and criminal networks.

IBM ships a companion file listing the laundering patterns its simulator
injected, each a block of transactions bracketed by

    BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 12 hops
    <transaction rows, same 11-column layout as the transaction CSV>
    END LAUNDERING ATTEMPT - CYCLE

This is scenario ground truth that would otherwise have to be invented: the
typology name, which transactions belong to which instance, and which accounts
form a network together. It is the difference between `criminal_networks.csv`
being evidence and being a guess.

Two facts about the file shape it:

- The last block has no closing `END` — 493 `BEGIN` lines against 492 `END`
  lines. A parser that requires the terminator loses a whole pattern.
- Its 4,087 transactions are far fewer than the 35,230 rows the transaction file
  marks `is_laundering=1`, so the patterns file documents a *subset* of the
  labelled activity. Membership in it means "part of a named typology instance",
  not "all the laundering there is".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abm.profiling.ibm_reader import COLUMN_NAMES

BEGIN_PREFIX = "BEGIN LAUNDERING ATTEMPT - "
END_PREFIX = "END LAUNDERING ATTEMPT - "

# "CYCLE:  Max 12 hops" -> typology CYCLE, parameter "Max 12 hops"
_TYPOLOGY_PATTERN = re.compile(r"^(?P<typology>[A-Z\-]+)(?::\s*(?P<parameter>.+))?$")


def normalize_account_key(bank: str, account: str) -> str:
    """Match the normalization used everywhere else: strip the bank's zero padding."""
    stripped = bank.lstrip("0") or "0"
    return f"{stripped}:{account}"


@dataclass(slots=True)
class PatternInstance:
    """One named laundering attempt and the transactions that make it up."""

    index: int
    typology: str
    typology_parameter: str | None
    transactions: list[dict[str, str]] = field(default_factory=list)
    closed: bool = False

    @property
    def accounts(self) -> set[str]:
        """Account keys, normalized the same way as everywhere else.

        The patterns file writes bank ids with the same inconsistent zero padding
        as the transaction file, so `0031224:812E2A1A0` here is `31224:812E2A1A0`
        in the behavior profile. Skipping the normalization makes every pattern
        account look absent from the profile, which silently reduces the
        criminal-network selection to nothing.
        """
        keys: set[str] = set()
        for row in self.transactions:
            keys.add(normalize_account_key(row["from_bank"], row["from_account"]))
            keys.add(normalize_account_key(row["to_bank"], row["to_account"]))
        return keys

    def summary(self) -> dict[str, Any]:
        timestamps = sorted(row["timestamp"] for row in self.transactions)
        return {
            "typology": self.typology,
            "typology_parameter": self.typology_parameter,
            "transaction_count": len(self.transactions),
            "account_count": len(self.accounts),
            "first_event": timestamps[0] if timestamps else None,
            "last_event": timestamps[-1] if timestamps else None,
            "explicitly_closed": self.closed,
        }


def _parse_header(line: str) -> tuple[str, str | None]:
    match = _TYPOLOGY_PATTERN.match(line.strip())
    if not match:
        return line.strip(), None
    return match.group("typology"), (match.group("parameter") or None)


def parse_patterns(path: Path, *, encoding: str = "utf-8") -> list[PatternInstance]:
    """Read every pattern block, including the unterminated final one."""
    instances: list[PatternInstance] = []
    current: PatternInstance | None = None

    with path.open("r", encoding=encoding) as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue

            if line.startswith(BEGIN_PREFIX):
                typology, parameter = _parse_header(line[len(BEGIN_PREFIX) :])
                current = PatternInstance(index=len(instances) + 1, typology=typology, typology_parameter=parameter)
                instances.append(current)
                continue

            if line.startswith(END_PREFIX):
                if current is not None:
                    current.closed = True
                current = None
                continue

            if current is None:
                continue

            values = line.split(",")
            if len(values) != len(COLUMN_NAMES):
                continue
            current.transactions.append(dict(zip(COLUMN_NAMES, values, strict=True)))

    return [instance for instance in instances if instance.transactions]


def pattern_accounts(instances: list[PatternInstance]) -> dict[str, list[int]]:
    """Account key to the pattern indices it appears in.

    An account can belong to more than one instance. That is not an error in the
    data — a mule reused across two attempts is realistic — but it does mean
    networks are not a clean partition, and the split logic has to keep every
    instance an account touches on the same side.
    """
    membership: dict[str, list[int]] = {}
    for instance in instances:
        for key in instance.accounts:
            membership.setdefault(key, []).append(instance.index)
    return membership


def summarize(instances: list[PatternInstance]) -> dict[str, Any]:
    typologies: dict[str, int] = {}
    for instance in instances:
        typologies[instance.typology] = typologies.get(instance.typology, 0) + 1

    membership = pattern_accounts(instances)
    shared = {key: indices for key, indices in membership.items() if len(indices) > 1}
    return {
        "instances": len(instances),
        "transactions": sum(len(instance.transactions) for instance in instances),
        "distinct_accounts": len(membership),
        "accounts_in_multiple_instances": len(shared),
        "unterminated_instances": sum(1 for instance in instances if not instance.closed),
        "typologies": dict(sorted(typologies.items(), key=lambda item: -item[1])),
    }
