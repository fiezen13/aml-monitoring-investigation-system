"""Test whether behavioral archetypes accidentally encode the laundering label.

This is the only place in the archetype pipeline that reads `is_laundering`, and
it reads it strictly *after* the clusters exist. Deriving archetypes without the
label and then checking them against it is a validation. Using the label to form
them would be leakage. The order is the whole point.

What it measures: for each archetype, the share of its accounts that are touched
by at least one laundering transaction, and the lift of that share over the
population base rate. An archetype with very high lift is a warning — matching
synthetic KYC customers through it would correlate KYC attributes with the label
before any AML scenario is generated, which is exactly the failure Phase 14 is
meant to catch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from abm.profiling.ibm_behavior import account_key
from abm.profiling.ibm_reader import COLUMN_NAMES, convert_column, iter_batches


def collect_flagged_accounts(path: Path, *, max_rows: int | None = None) -> set[str]:
    """Account keys touched by at least one laundering transaction.

    Both endpoints of a flagged transaction are collected. This is the broadest
    reasonable account-level label and therefore the most demanding leakage test:
    a narrower definition would find less association by construction.
    """
    flagged: set[str] = set()
    for batch in iter_batches(path, max_rows=max_rows):
        columns = {name: batch.column(index) for index, name in enumerate(COLUMN_NAMES)}
        label = convert_column(columns["is_laundering"], "is_laundering")
        mask = pc.equal(label, 1)
        if not pc.any(mask).as_py():
            continue
        for bank, account in (("from_bank", "from_account"), ("to_bank", "to_account")):
            keys = account_key(pc.filter(columns[bank], mask), pc.filter(columns[account], mask))
            flagged.update(value for value in keys.to_pylist() if value is not None)
    return flagged


def evaluate_archetype_leakage(
    archetypes_csv: Path,
    transactions_csv: Path,
    *,
    report: Path,
    max_rows: int | None = None,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    flagged = collect_flagged_accounts(transactions_csv, max_rows=max_rows)

    table = pacsv.read_csv(
        str(archetypes_csv),
        convert_options=pacsv.ConvertOptions(include_columns=["account_key", "archetype", "entity_kind"]),
    )
    keys = table.column("account_key").to_pylist()
    archetypes = table.column("archetype").to_pylist()

    totals: dict[str, int] = {}
    positives: dict[str, int] = {}
    for key, archetype in zip(keys, archetypes, strict=True):
        totals[archetype] = totals.get(archetype, 0) + 1
        if key in flagged:
            positives[archetype] = positives.get(archetype, 0) + 1

    clustered_positive = sum(positives.values())
    base_rate = clustered_positive / len(keys) if keys else 0.0

    rows = []
    for archetype in sorted(totals):
        total = totals[archetype]
        positive = positives.get(archetype, 0)
        rate = positive / total
        rows.append(
            {
                "archetype": archetype,
                "accounts": total,
                "flagged_accounts": positive,
                "flagged_rate": rate,
                "lift_vs_base": (rate / base_rate) if base_rate else None,
            }
        )

    lifts = [row["lift_vs_base"] for row in rows if row["lift_vs_base"] is not None]
    verdict = _verdict(max(lifts) if lifts else 0.0)

    summary = {
        "evaluated_at": started.isoformat(timespec="seconds"),
        "method": (
            "Archetypes were derived without the label. This check reads the label "
            "afterwards and measures association only."
        ),
        "account_label_definition": "touched by at least one is_laundering=1 transaction, either endpoint",
        "flagged_accounts_in_source": len(flagged),
        "clustered_accounts": len(keys),
        "clustered_flagged_accounts": clustered_positive,
        "base_rate": base_rate,
        "by_archetype": rows,
        "max_lift": max(lifts) if lifts else None,
        "verdict": verdict,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _verdict(max_lift: float) -> str:
    """Judge the association, with the thresholds stated rather than implied."""
    if max_lift >= 10:
        return (
            "FAIL: an archetype concentrates the label more than 10x. Matching KYC "
            "through these archetypes would correlate KYC attributes with the label."
        )
    if max_lift >= 3:
        return (
            "WARN: an archetype concentrates the label more than 3x. Usable, but the "
            "matcher must not let archetype alone determine AML actor selection."
        )
    return (
        "PASS: no archetype concentrates the label more than 3x. Archetype membership "
        "is a weak predictor, which is what a label-free derivation should produce."
    )


def account_label_table(flagged: set[str]) -> pa.Table:
    """Materialize the account-level label for the ground-truth subtree."""
    ordered = sorted(flagged)
    return pa.table(
        {
            "account_key": pa.array(ordered, pa.string()),
            "label_type": pa.array(["IBM_AML_INVOLVEMENT"] * len(ordered), pa.string()),
            "label_value": pa.array([1] * len(ordered), pa.int8()),
            "source": pa.array(["IBM_AML"] * len(ordered), pa.string()),
        }
    )
