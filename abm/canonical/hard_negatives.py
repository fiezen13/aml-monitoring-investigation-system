"""Phase 15 — legitimate activity that looks like laundering.

A dataset where every fan-in is criminal teaches a model that fan-in is criminal.
Hard negatives are the correction: legitimate customers whose behavior collides
with the simplest AML rules, labelled `LEGITIMATE` in ground truth and left
completely unremarkable in Bank View.

The six families follow `docs/abm/HARD_NEGATIVES.md`, which survived the Phase 0
cleanup because its analysis holds regardless of how the transactions are
sourced.

| Family | Legitimate explanation | Collides with |
|---|---|---|
| `SALARY_DISBURSEMENT` | A business pays its staff | Fan-out, many beneficiaries, rapid balance decline |
| `MARKETPLACE_SELLER` | Many small customer payments, then settlement | Fan-in, bursty receipts, counterparty diversity |
| `FAMILY_REMITTANCE_HUB` | One member collects and redistributes family funds | Hub topology, rapid redistribution |
| `SEASONAL_BUSINESS` | A short high-volume trading peak | Sudden peer deviation |
| `PROPERTY_OR_INSURANCE` | A documented large one-off receipt | Large inbound then rapid outflows |
| `TREASURY_SWEEP` | Related businesses moving liquidity | High-value pass-through, circular movement |

## Two rules that make them work

**Hard-negative entities are excluded from AML actor selection.** An entity
cannot be both a designed false positive and a true positive; if it were, the
label would contradict the family and no evaluation could interpret either.

**They are appended as simulation extensions, never by overwriting IBM rows.**
IBM's transactions are the evidenced backbone. Rewriting them to manufacture a
collision would corrupt the one part of the release with real provenance, so
hard-negative transactions are new rows carrying `source=P022_SIMULATION`, and
the manifest counts them separately.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

HARD_NEGATIVE_ID_FORMAT = "HNG-{:06d}"

FAMILIES = (
    "SALARY_DISBURSEMENT",
    "MARKETPLACE_SELLER",
    "FAMILY_REMITTANCE_HUB",
    "SEASONAL_BUSINESS",
    "PROPERTY_OR_INSURANCE",
    "TREASURY_SWEEP",
)

# Benchmark coverage quotas, not incidence estimates. Nothing here claims how
# often these episodes happen in a real Vietnamese bank.
ASSUME_FAMILY_QUOTA = {
    "SALARY_DISBURSEMENT": 40,
    "MARKETPLACE_SELLER": 55,
    "FAMILY_REMITTANCE_HUB": 45,
    "SEASONAL_BUSINESS": 30,
    "PROPERTY_OR_INSURANCE": 35,
    "TREASURY_SWEEP": 20,
}

_FAMILY_SHAPE: dict[str, dict[str, Any]] = {
    "SALARY_DISBURSEMENT": {
        "entity": "BUSINESS",
        "legs": (12, 40),
        "direction": "OUT",
        "amount_multiple": (0.02, 0.06),
        "days": (1, 2),
        "explanation": "Registered business funds payroll and pays an employee cohort",
        "collision": "Fan-out to many beneficiaries within one or two days",
    },
    "MARKETPLACE_SELLER": {
        "entity": "BUSINESS",
        "legs": (25, 90),
        "direction": "IN",
        "amount_multiple": (0.005, 0.03),
        "days": (3, 10),
        "explanation": "Online seller receives many small customer payments",
        "collision": "Fan-in with high counterparty diversity and bursty receipts",
    },
    "FAMILY_REMITTANCE_HUB": {
        "entity": "CUSTOMER",
        "legs": (8, 22),
        "direction": "BOTH",
        "amount_multiple": (0.08, 0.25),
        "days": (2, 6),
        "explanation": "Household member collects and redistributes family funds",
        "collision": "Hub topology with rapid redistribution of received funds",
    },
    "SEASONAL_BUSINESS": {
        "entity": "BUSINESS",
        "legs": (30, 80),
        "direction": "IN",
        "amount_multiple": (0.01, 0.05),
        "days": (4, 8),
        "explanation": "Short high-volume seasonal trading peak",
        "collision": "Sudden deviation from the account's own peer baseline",
    },
    "PROPERTY_OR_INSURANCE": {
        "entity": "CUSTOMER",
        "legs": (3, 8),
        "direction": "BOTH",
        "amount_multiple": (1.5, 6.0),
        "days": (1, 5),
        "explanation": "Documented property sale or insurance settlement",
        "collision": "Large inbound followed by rapid onward outflows",
    },
    "TREASURY_SWEEP": {
        "entity": "BUSINESS",
        "legs": (6, 18),
        "direction": "BOTH",
        "amount_multiple": (0.4, 1.2),
        "days": (2, 7),
        "explanation": "Related businesses sweep liquidity between accounts",
        "collision": "High-value pass-through and circular movement",
    },
}


@dataclass(slots=True)
class HardNegativeEpisode:
    hard_negative_id: str
    family: str
    entity_id: str
    entity_type: str
    account_id: str
    legs: list[dict[str, Any]]
    first_day: int
    last_day: int
    explanation: str
    collision: str


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def generate_episodes(
    accounts: list[dict[str, Any]],
    excluded_entities: set[str],
    *,
    day_range: tuple[int, int],
    seed: int,
) -> list[HardNegativeEpisode]:
    """Create one episode per quota slot on an eligible account.

    `excluded_entities` holds every entity involved in a laundering network. They
    are skipped, so no entity is both a designed false positive and a true one.
    """
    rng = _rng(seed, "hard_negatives")
    first_day, last_day = day_range

    by_type: dict[str, list[dict[str, Any]]] = {"CUSTOMER": [], "BUSINESS": []}
    for account in accounts:
        if account["owner_id"] in excluded_entities:
            continue
        if account.get("target_monthly_inflow_vnd") is None:
            continue
        by_type.setdefault(account["owner_type"], []).append(account)

    used: set[str] = set()
    episodes: list[HardNegativeEpisode] = []

    for family in FAMILIES:
        shape = _FAMILY_SHAPE[family]
        pool = [account for account in by_type.get(shape["entity"], []) if account["account_id"] not in used]
        if not pool:
            continue
        quota = min(ASSUME_FAMILY_QUOTA[family], len(pool))
        picks = rng.choice(len(pool), size=quota, replace=False)

        for pick in picks:
            account = pool[int(pick)]
            used.add(account["account_id"])
            baseline = float(account["target_monthly_inflow_vnd"])

            leg_count = int(rng.integers(shape["legs"][0], shape["legs"][1] + 1))
            span = int(rng.integers(shape["days"][0], shape["days"][1] + 1))
            start = int(rng.integers(first_day, max(first_day + 1, last_day - span)))

            legs = []
            for _ in range(leg_count):
                multiple = rng.uniform(*shape["amount_multiple"])
                if shape["direction"] == "BOTH":
                    inbound = bool(rng.random() < 0.5)
                else:
                    inbound = shape["direction"] == "IN"
                legs.append(
                    {
                        "inbound": inbound,
                        "amount_vnd": round(baseline * multiple, 2),
                        "day": start + int(rng.integers(0, span)),
                    }
                )

            episodes.append(
                HardNegativeEpisode(
                    hard_negative_id=HARD_NEGATIVE_ID_FORMAT.format(len(episodes) + 1),
                    family=family,
                    entity_id=account["owner_id"],
                    entity_type=account["owner_type"],
                    account_id=account["account_id"],
                    legs=legs,
                    first_day=min(leg["day"] for leg in legs),
                    last_day=max(leg["day"] for leg in legs),
                    explanation=shape["explanation"],
                    collision=shape["collision"],
                )
            )
    return episodes


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_HARD_NEGATIVE_QUOTA",
            "description": "How many episodes of each family the release contains.",
            "why_not_evidenced": (
                "Benchmark coverage decision, not an incidence estimate. No source "
                "says how often a Vietnamese bank sees a marketplace seller that "
                "trips a fan-in rule."
            ),
            "confidence": "governance",
        },
        {
            "assumption_id": "ASSUME_HARD_NEGATIVE_SHAPE",
            "description": "Leg counts, amount multiples, and durations per family.",
            "why_not_evidenced": (
                "Chosen so each family collides with the rule it is meant to "
                "collide with. Shapes are design targets, not measurements."
            ),
            "confidence": "governance",
        },
    ]
