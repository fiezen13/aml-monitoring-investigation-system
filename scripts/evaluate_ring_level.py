#!/usr/bin/env python3
"""Score transactions, then report recall at transaction, account AND ring level.

Why this exists
---------------
Every published result on the IBM AML data is transaction-level, because the
labels are per-transaction. But an AML team does not open a case on a transaction
— it opens one on an account, and what it really wants to know is whether the
laundering *scheme* was caught at all. A ring with ten transactions is caught the
moment one of them is alerted; an investigator finds the rest.

Transaction-level recall therefore understates operational performance. This
script measures all three levels on the same scores so the gap is visible.

Ground truth for rings comes from the IBM Patterns file, which lists the exact
transactions belonging to each laundering attempt.

Usage:
  python scripts/evaluate_ring_level.py \
    --db data/processed/hi_medium.duckdb \
    --patterns data/raw/ibm-aml/HI-Medium_Patterns.txt \
    --report-out reports/edge-benchmark/hi_medium_ring_level.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_edge_level import (  # noqa: E402
    BASIC_FEATURES,
    EDA_BANNED_FEATURES,
    GRAPH_FEATURES,
    _fit,
    build_features,
    run_data_quality,
)

BEGIN_RE = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Za-z0-9_\-]+)")
END_RE = re.compile(r"^END LAUNDERING ATTEMPT")
# The config the benchmark selects on validation for the graph feature sets.
CONFIG = {"max_iter": 800, "max_leaf_nodes": 127, "learning_rate": 0.05, "class_weight": None}
BUDGETS = (100, 250, 500, 1000, 2500, 5000, 12239, 25000, 50000)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--patterns", type=Path, required=True)
    p.add_argument("--report-out", type=Path, required=True)
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument("--degree-cap", type=int, default=200)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--memory-limit", default="10GB")
    p.add_argument(
        "--policy-compliant",
        action="store_true",
        help="Drop the features the team EDA bans (channel_code, hour_of_day).",
    )
    return p.parse_args()


def account_key(bank: str, account: str) -> str:
    """Mirror src.data.schemas.make_account_key: numeric banks lose leading zeros."""
    bank = bank.strip()
    if bank.isdigit():
        bank = str(int(bank))
    return f"{bank}:{account.strip()}"


def parse_rings(path: Path) -> tuple[pd.DataFrame, dict]:
    """One row per (ring, transaction). Tolerates a truncated final block."""
    rows: list[dict] = []
    stats = {"blocks_begun": 0, "blocks_closed": 0, "dropped_incomplete": 0, "malformed_lines": 0}
    ring_id = -1
    pattern_type = ""
    open_rows: list[dict] = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        begin = BEGIN_RE.match(line)
        if begin:
            if open_rows:  # previous block never closed
                stats["dropped_incomplete"] += 1
                open_rows = []
            ring_id += 1
            stats["blocks_begun"] += 1
            pattern_type = begin.group(1).upper()
            continue
        if END_RE.match(line):
            rows.extend(open_rows)
            open_rows = []
            stats["blocks_closed"] += 1
            continue
        parts = line.split(",")
        if len(parts) < 11:
            stats["malformed_lines"] += 1
            continue
        try:
            open_rows.append(
                {
                    "ring_id": ring_id,
                    "pattern_type": pattern_type,
                    "occurred_at": datetime.strptime(parts[0], "%Y/%m/%d %H:%M").replace(tzinfo=UTC),
                    "from_account_key": account_key(parts[1], parts[2]),
                    "to_account_key": account_key(parts[3], parts[4]),
                    "amount_paid_orig": float(parts[7]),
                }
            )
        except (ValueError, IndexError):
            stats["malformed_lines"] += 1
    if open_rows:
        stats["dropped_incomplete"] += 1
    return pd.DataFrame(rows), stats


def level_metrics(y: np.ndarray, score: np.ndarray, budgets: tuple[int, ...]) -> list[dict]:
    order = np.argsort(-score, kind="mergesort")
    hits = np.cumsum(y[order])
    total = int(y.sum())
    out = []
    for budget in budgets:
        if budget > len(y):
            continue
        caught = int(hits[budget - 1])
        out.append(
            {
                "alerts": budget,
                "caught": caught,
                "missed": total - caught,
                "recall": round(caught / total, 4) if total else None,
                "precision": round(caught / budget, 4),
            }
        )
    return out


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    print("[1/5] Parsing the ground-truth pattern file ...", flush=True)
    rings, ring_stats = parse_rings(args.patterns)
    print(
        f"      {ring_stats['blocks_begun']} blocks, {ring_stats['blocks_closed']} closed, "
        f"{ring_stats['dropped_incomplete']} incomplete dropped, "
        f"{len(rings):,} member transactions",
        flush=True,
    )

    print("[2/5] Building features ...", flush=True)
    features = BASIC_FEATURES + GRAPH_FEATURES
    if args.policy_compliant:
        features = [f for f in features if f not in EDA_BANNED_FEATURES]
    con = duckdb.connect(str(args.db), read_only=True)
    for statement in (
        "SET TimeZone='UTC'",
        f"SET threads={int(args.threads)}",
        f"SET memory_limit='{args.memory_limit}'",
        "SET preserve_insertion_order=false",
    ):
        con.execute(statement)
    frame, _ = build_features(con, args.window_days, args.degree_cap, 24)
    dq = run_data_quality(con, frame, features)
    if not dq["ok"]:
        con.close()
        raise RuntimeError("; ".join(dq["hard_failures"]))

    # Roll-ups need identity columns alongside the features. They must come from
    # ONE query: preserve_insertion_order is off, so two separate SELECTs against
    # the same table are not guaranteed to return rows in the same order, and
    # stitching them by position would silently mis-pair every row.
    columns = ", ".join(f'"{name}"' for name in features)
    frame = con.execute(
        f"SELECT split, y, occurred_at, from_account_key, to_account_key, amount_paid_orig, {columns} FROM features"
    ).fetchdf()
    con.close()
    frame[features] = frame[features].astype(np.float32).replace([np.inf, -np.inf], 0.0).fillna(0.0)

    print("[3/5] Fitting on train and scoring test ...", flush=True)
    train = frame[frame.split == "train"]
    test = frame[frame.split == "test"].reset_index(drop=True)
    model = _fit(CONFIG, features, train, seed=42)
    test["score"] = model.predict_proba(test[features].to_numpy(dtype=np.float32))[:, 1]
    print(f"      test {len(test):,} rows, {int(test.y.sum()):,} laundering", flush=True)

    print("[4/5] Rolling up to account and ring level ...", flush=True)
    result: dict = {
        "schema_version": "fin07.ring_benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "database": str(args.db),
        "policy_compliant": bool(args.policy_compliant),
        "n_features": len(features),
        "pattern_file": {"path": str(args.patterns), **ring_stats},
        "note": "A ring counts as caught when at least one of its transactions is alerted.",
    }

    # --- transaction level
    result["transaction_level"] = {
        "units": int(len(test)),
        "positives": int(test.y.sum()),
        "operating_points": level_metrics(test.y.to_numpy(), test.score.to_numpy(), BUDGETS),
    }

    # --- account level: an account is positive if it touches any laundering tx in test
    long = pd.concat(
        [
            test[["from_account_key", "y", "score"]].rename(columns={"from_account_key": "acct"}),
            test[["to_account_key", "y", "score"]].rename(columns={"to_account_key": "acct"}),
        ],
        ignore_index=True,
    )
    per_account = long.groupby("acct", as_index=False).agg(y=("y", "max"), score=("score", "max"))
    result["account_level"] = {
        "units": int(len(per_account)),
        "positives": int(per_account.y.sum()),
        "operating_points": level_metrics(per_account.y.to_numpy(), per_account.score.to_numpy(), BUDGETS),
    }

    # --- ring level: match pattern transactions onto scored test transactions
    keys = ["occurred_at", "from_account_key", "to_account_key", "amount_paid_orig"]
    test_keyed = test[[*keys, "score"]].copy()
    for part in (rings, test_keyed):
        part["occurred_at"] = pd.to_datetime(part["occurred_at"], utc=True)
        part["amount_paid_orig"] = part["amount_paid_orig"].round(2)
    matched = rings.merge(test_keyed, on=keys, how="inner")
    per_ring = matched.groupby("ring_id", as_index=False).agg(
        score=("score", "max"), pattern_type=("pattern_type", "first"), n_tx=("score", "size")
    )
    result["ring_level"] = {
        "rings_in_file": int(rings.ring_id.nunique()),
        "rings_present_in_test": int(len(per_ring)),
        "member_transactions_matched": int(len(matched)),
        "match_rate": round(len(matched) / len(rings), 4) if len(rings) else None,
        "median_transactions_per_ring_in_test": float(per_ring.n_tx.median()) if len(per_ring) else None,
    }
    # A ring is caught if any member transaction lands in the top-K alerts.
    order = np.argsort(-test.score.to_numpy(), kind="mergesort")
    caught_curve = []
    for budget in BUDGETS:
        if budget > len(test):
            continue
        cutoff = float(test.score.to_numpy()[order[budget - 1]])
        caught = int((per_ring.score >= cutoff).sum())
        caught_curve.append(
            {
                "alerts": budget,
                "rings_caught": caught,
                "rings_missed": int(len(per_ring)) - caught,
                "ring_recall": round(caught / len(per_ring), 4) if len(per_ring) else None,
            }
        )
    result["ring_level"]["operating_points"] = caught_curve
    if len(per_ring):
        by_type = []
        top_cutoff = float(test.score.to_numpy()[order[min(5000, len(test)) - 1]])
        for name, group in per_ring.groupby("pattern_type"):
            by_type.append(
                {
                    "pattern_type": name,
                    "rings": int(len(group)),
                    "caught_at_5000_alerts": int((group.score >= top_cutoff).sum()),
                    "recall": round(float((group.score >= top_cutoff).mean()), 4),
                }
            )
        result["ring_level"]["by_pattern_type_at_5000_alerts"] = sorted(by_type, key=lambda r: -r["rings"])

    print("[5/5] Writing report ...", flush=True)
    result["seconds"] = round(time.perf_counter() - started, 1)
    args.report_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "ring_level"}, indent=2)[:1500])
    print(json.dumps(result["ring_level"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
