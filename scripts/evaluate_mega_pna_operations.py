#!/usr/bin/env python3
"""Evaluate MEGA-PNA scores at transaction, ring, workload and evidence level."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_ring_level import account_key, parse_rings  # noqa: E402
from src.mega_pna.metrics import budget_metrics  # noqa: E402

BUDGETS = [100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--raw-transactions", type=Path, required=True)
    parser.add_argument("--patterns", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--evidence-jsonl", type=Path)
    parser.add_argument("--cases-per-investigator-day", type=float, default=25.0)
    return parser.parse_args()


def load_scored_transactions(predictions: Path, raw: Path) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=true")
    frame = con.execute(
        """
        WITH raw_numbered AS (
            SELECT row_number() OVER () - 1 AS source_edge_id, *
            FROM read_csv(?, all_varchar=true, header=true)
        )
        SELECT p.source_edge_id, p.is_laundering, p.score,
               strptime(r."Timestamp", '%Y/%m/%d %H:%M') AS occurred_at,
               r."From Bank" AS from_bank, r."Account" AS from_account,
               r."To Bank" AS to_bank, r."Account_1" AS to_account,
               CAST(r."Amount Paid" AS DOUBLE) AS amount_paid
        FROM read_parquet(?) p
        JOIN raw_numbered r USING (source_edge_id)
        """,
        [str(raw), str(predictions)],
    ).fetchdf()
    con.close()
    frame["from_account_key"] = [
        account_key(bank, account) for bank, account in zip(frame.from_bank, frame.from_account)
    ]
    frame["to_account_key"] = [account_key(bank, account) for bank, account in zip(frame.to_bank, frame.to_account)]
    frame["occurred_at"] = pd.to_datetime(frame.occurred_at, utc=True)
    frame["amount_paid"] = frame.amount_paid.round(2)
    return frame


def ring_metrics(scored: pd.DataFrame, patterns_path: Path) -> dict[str, object]:
    rings, parse_stats = parse_rings(patterns_path)
    if rings.empty:
        return {"parse": parse_stats, "rings_present_in_test": 0, "operating_points": []}
    rings["occurred_at"] = pd.to_datetime(rings.occurred_at, utc=True)
    rings["amount_paid_orig"] = rings.amount_paid_orig.round(2)
    keyed = scored.rename(columns={"amount_paid": "amount_paid_orig"})
    keys = [
        "occurred_at",
        "from_account_key",
        "to_account_key",
        "amount_paid_orig",
    ]
    matched = rings.merge(keyed[[*keys, "score"]], on=keys, how="inner")
    per_ring = matched.groupby("ring_id", as_index=False).agg(
        score=("score", "max"), pattern_type=("pattern_type", "first")
    )
    order = np.argsort(-scored.score.to_numpy(), kind="stable")
    points = []
    for budget in BUDGETS:
        if budget > len(scored):
            continue
        cutoff = float(scored.score.to_numpy()[order[budget - 1]])
        caught = int((per_ring.score >= cutoff).sum())
        points.append(
            {
                "alerts": budget,
                "rings_caught": caught,
                "ring_recall": caught / len(per_ring) if len(per_ring) else None,
            }
        )
    return {
        "parse": parse_stats,
        "rings_in_file": int(rings.ring_id.nunique()),
        "rings_present_in_test": int(len(per_ring)),
        "member_transactions_matched": int(len(matched)),
        "operating_points": points,
    }


def workload_metrics(scored: pd.DataFrame, capacity: float) -> list[dict[str, object]]:
    days = max(1, int(scored.occurred_at.dt.floor("D").nunique()))
    rows = []
    for budget in BUDGETS:
        if budget > len(scored):
            continue
        per_day = budget / days
        rows.append(
            {
                "alerts": budget,
                "test_days": days,
                "cases_per_day": per_day,
                "cases_per_investigator_day": capacity,
                "investigators_required": math.ceil(per_day / capacity),
            }
        )
    return rows


def evidence_metrics(scored: pd.DataFrame, evidence_path: Path | None) -> dict[str, object]:
    if evidence_path is None:
        return {
            "available": False,
            "reason": "No --evidence-jsonl was supplied; coverage was not inferred.",
        }
    max_budget = min(max(BUDGETS), len(scored))
    top = scored.nlargest(max_budget, "score")[
        ["source_edge_id", "from_account_key", "to_account_key", "occurred_at", "amount_paid"]
    ].copy()
    top["occurred_at"] = top.occurred_at.dt.tz_convert("UTC").dt.tz_localize(None)
    con = duckdb.connect()
    con.register("scored_top", top)
    attached_ids = con.execute(
        """
        SELECT DISTINCT s.source_edge_id
        FROM scored_top s
        JOIN read_json_auto(?, maximum_object_size=10485760) e ON true
        JOIN UNNEST(e.hops) AS u(h)
          ON h.from_account_key = s.from_account_key
         AND h.to_account_key = s.to_account_key
         AND CAST(h.occurred_at AS TIMESTAMP) = s.occurred_at
         AND round(h.amount, 2) = s.amount_paid
        WHERE e.detected_pattern IS NOT NULL AND e.evidence_id IS NOT NULL
        """,
        [str(evidence_path)],
    ).fetchnumpy()["source_edge_id"]
    con.close()
    attachment = scored.source_edge_id.isin(attached_ids).to_numpy(dtype=bool)
    order = np.argsort(-scored.score.to_numpy(), kind="stable")
    points = []
    for budget in BUDGETS:
        if budget > len(scored):
            continue
        count = int(attachment[order[:budget]].sum())
        points.append(
            {
                "alerts": budget,
                "with_named_typology_and_subgraph": count,
                "attachment_rate": count / budget,
            }
        )
    return {
        "available": True,
        "definition": "Exact scored transaction appears as a hop in named graph evidence.",
        "operating_points": points,
    }


def main() -> int:
    args = parse_args()
    scored = load_scored_transactions(args.predictions, args.raw_transactions)
    labels = scored.is_laundering.to_numpy(dtype=np.int64)
    scores = scored.score.to_numpy(dtype=np.float64)
    report = {
        "schema_version": "fin07.mega_pna.operations.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "predictions": str(args.predictions),
        "test_rows": int(len(scored)),
        "test_positives": int(labels.sum()),
        "transaction_level": budget_metrics(labels, scores, BUDGETS),
        "ring_level": ring_metrics(scored, args.patterns),
        "workload": workload_metrics(scored, args.cases_per_investigator_day),
        "evidence": evidence_metrics(scored, args.evidence_jsonl),
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
