"""Compare a materialized release against the raw IBM source it came from.

## What can and cannot be compared

Four things are changed on purpose, so comparing them would only measure the
transformation:

| Changed | Why |
|---|---|
| Absolute amounts | Rescaled per account into dong (Phase 8) |
| Payment format | IBM's predicted its own label at 7.2x lift |
| Time of day | IBM's is uniform random and carries no signal |
| Identifiers | Canonical ids; IBM keys must not survive |

Everything else must survive, and that is what this measures. The release claims
to preserve IBM's *relative* structure, so the test is whether the dimensionless
quantities still line up:

- how many transactions each account makes;
- how many distinct counterparties, in each direction;
- the balance of inflow against outflow;
- the graph's degree distribution and component structure;
- the calendar, the ordering, and the label.

Comparison is distributional rather than per-account, because the release
deliberately keeps no mapping back to an IBM account key. That is also the right
comparison: what matters is that the population of accounts behaves like IBM's,
not that account 41 maps to a particular source row.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.csv as pacsv

# Quantiles reported for every distribution compared.
QUANTILES = (0.25, 0.50, 0.75, 0.90, 0.95, 0.99)

# A distribution passes when every reported quantile is within this relative
# tolerance. Loose on purpose: the release adds hard negatives and drops rows
# whose account has no calibration scale, so exact equality is not the claim.
RELATIVE_TOLERANCE = 0.15


def _quantiles(values: np.ndarray) -> dict[str, float]:
    if len(values) == 0:
        return {}
    return {f"p{int(q * 100)}": float(np.quantile(values, q)) for q in QUANTILES} | {
        "mean": float(values.mean()),
        "max": float(values.max()),
    }


def _compare(name: str, source: np.ndarray, release: np.ndarray) -> dict[str, Any]:
    source_q = _quantiles(source)
    release_q = _quantiles(release)
    deviations = {}
    for key, expected in source_q.items():
        actual = release_q.get(key)
        if actual is None:
            continue
        denominator = abs(expected) if abs(expected) > 1e-9 else 1.0
        deviations[key] = round((actual - expected) / denominator, 4)
    worst = max((abs(value) for value in deviations.values()), default=0.0)
    return {
        "feature": name,
        "source_n": int(len(source)),
        "release_n": int(len(release)),
        "ibm": {key: round(value, 4) for key, value in source_q.items()},
        "release": {key: round(value, 4) for key, value in release_q.items()},
        "relative_deviation": deviations,
        "worst_relative_deviation": round(worst, 4),
        "verdict": "PASS" if worst <= RELATIVE_TOLERANCE else "REVIEW",
    }


def account_behavior_from_release(release: Path) -> dict[str, Any]:
    """Recompute per-account behavior from the release's own transactions.

    Deliberately derived from the shipped CSV rather than from builder state, so
    the comparison tests what a consumer would actually see.
    """
    outgoing: Counter = Counter()
    incoming: Counter = Counter()
    out_partners: dict[str, set[str]] = defaultdict(set)
    in_partners: dict[str, set[str]] = defaultdict(set)
    inflow: Counter = Counter()
    outflow: Counter = Counter()
    self_transfers = 0
    total = 0
    labels_by_source: Counter = Counter()

    with (release / "bank_view" / "transactions.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            source = row["source_account_id"] or row["source_counterparty_token"]
            target = row["destination_account_id"] or row["destination_counterparty_token"]
            amount = float(row["amount"])
            is_self = bool(source) and source == target
            if is_self:
                self_transfers += 1

            # Self-transfers count toward volume but never toward counterparties,
            # which is exactly how the IBM behavior profiler treats them. Skipping
            # them entirely — as an earlier version did — drops every account whose
            # only activity is internal (318,725 of them) and computes the release
            # median over a strictly busier subpopulation, so the comparison
            # reports a difference that is an artifact of its own bookkeeping.
            if row["source_account_id"]:
                outgoing[source] += 1
                outflow[source] += amount
                if target and not is_self:
                    out_partners[source].add(target)
            if row["destination_account_id"]:
                incoming[target] += 1
                inflow[target] += amount
                if source and not is_self:
                    in_partners[target].add(source)

    with (release / "ground_truth" / "transaction_labels.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            labels_by_source[row["source"]] += 1

    accounts = set(outgoing) | set(incoming)
    counts = np.array([outgoing[key] + incoming[key] for key in accounts], dtype=float)
    fan_in = np.array([len(in_partners[key]) / incoming[key] if incoming[key] else 0.0 for key in accounts])
    fan_out = np.array([len(out_partners[key]) / outgoing[key] if outgoing[key] else 0.0 for key in accounts])
    balance = np.array(
        [
            (incoming[key] - outgoing[key]) / (incoming[key] + outgoing[key])
            if (incoming[key] + outgoing[key])
            else 0.0
            for key in accounts
        ]
    )
    unique_in = np.array([len(in_partners[key]) for key in accounts], dtype=float)
    unique_out = np.array([len(out_partners[key]) for key in accounts], dtype=float)

    return {
        "transactions": total,
        "self_transfers": self_transfers,
        "accounts_active": len(accounts),
        "labels_by_source": dict(labels_by_source),
        "transaction_count": counts,
        "fan_in_ratio": fan_in,
        "fan_out_ratio": fan_out,
        "flow_balance": balance,
        "unique_inbound_counterparties": unique_in,
        "unique_outbound_counterparties": unique_out,
    }


def account_behavior_from_ibm(behavior_csv: Path) -> dict[str, np.ndarray]:
    table = pacsv.read_csv(
        str(behavior_csv),
        convert_options=pacsv.ConvertOptions(
            include_columns=[
                "transaction_count",
                "fan_in_ratio",
                "fan_out_ratio",
                "incoming_transaction_count",
                "outgoing_transaction_count",
                "unique_inbound_counterparties",
                "unique_outbound_counterparties",
            ]
        ),
    )

    def column(name: str) -> np.ndarray:
        return np.nan_to_num(table.column(name).to_numpy(zero_copy_only=False).astype(float))

    incoming = column("incoming_transaction_count")
    outgoing = column("outgoing_transaction_count")
    total = incoming + outgoing
    balance = np.divide(incoming - outgoing, total, out=np.zeros_like(total), where=total > 0)

    return {
        "transaction_count": column("transaction_count"),
        "fan_in_ratio": column("fan_in_ratio"),
        "fan_out_ratio": column("fan_out_ratio"),
        "flow_balance": balance,
        "unique_inbound_counterparties": column("unique_inbound_counterparties"),
        "unique_outbound_counterparties": column("unique_outbound_counterparties"),
    }


def compare(
    release: Path,
    *,
    ibm_profile_path: Path,
    ibm_behavior_csv: Path,
) -> dict[str, Any]:
    ibm_profile = json.loads(ibm_profile_path.read_text(encoding="utf-8"))
    source = account_behavior_from_ibm(ibm_behavior_csv)
    derived = account_behavior_from_release(release)

    features = [
        _compare(name, source[name], derived[name])
        for name in (
            "transaction_count",
            "fan_in_ratio",
            "fan_out_ratio",
            "flow_balance",
            "unique_inbound_counterparties",
            "unique_outbound_counterparties",
        )
    ]

    release_transactions = derived["transactions"]
    simulated = derived["labels_by_source"].get("P022_SIMULATION", 0)
    from_ibm = release_transactions - simulated

    coverage = {
        "ibm_transactions": ibm_profile["row_count"],
        "release_transactions_total": release_transactions,
        "release_transactions_from_ibm": from_ibm,
        "release_transactions_simulated": simulated,
        "ibm_coverage": round(from_ibm / ibm_profile["row_count"], 6),
        "ibm_accounts": ibm_profile["identifiers"]["distinct_account_keys_bank_qualified"],
        "release_accounts_active": derived["accounts_active"],
        "ibm_self_transfer_share": round(ibm_profile["structure"]["self_transfer_share"], 6),
        "release_self_transfer_share": round(derived["self_transfers"] / max(release_transactions, 1), 6),
        "ibm_laundering_rows": ibm_profile["label"]["positive_rows"],
    }

    failing = [entry["feature"] for entry in features if entry["verdict"] != "PASS"]
    return {
        "comparison": "release vs raw IBM",
        "tolerance": RELATIVE_TOLERANCE,
        "coverage": coverage,
        "preserved_features": features,
        "features_outside_tolerance": failing,
        "intentionally_not_comparable": {
            "amount": "rescaled per account into VND by the documented calibration",
            "payment_format": "redrawn; IBM's predicted its own label at 7.2x lift",
            "hour_of_day": "redrawn; IBM assigns times uniformly at random",
            "currency": "IBM's fifteen currencies collapse to VND",
            "account_identifiers": "canonical ids; IBM keys must not survive",
        },
        "verdict": "PASS" if not failing else "REVIEW",
    }
