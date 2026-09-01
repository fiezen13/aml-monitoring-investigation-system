#!/usr/bin/env python3
"""Edge-level AML benchmark on the protocol used by the IBM AML literature.

Why this file exists
--------------------
The repo's existing benchmark (reports/fusion-v2/benchmark.json) scores
account-snapshots. Every published result on this dataset scores *transactions*
(edge classification), so the two cannot be compared. This script reproduces the
published protocol so our numbers sit on the same axis as the papers:

  unit    : one row per transaction
  split   : 60/20/20 temporal, by transaction ordered on timestamp
            (Altman et al., NeurIPS 2023 D&B, arXiv:2306.16424)
  metric  : minority-class F1, plus the full confusion matrix
  threshold: chosen on validation to maximise F1, then applied once to test

Published LI-Small minority-class F1 for reference:
  XGBoost, basic features    0.21 %   arXiv:2402.08593 table 4
  LightGBM, basic features   2.05 %   arXiv:2402.08593 table 4
  MLP                       14.59 %   arXiv:2306.16424 table 2
  LightGBM + GFP            20.83 %   arXiv:2402.08593 table 4
  XGBoost + GFP             27.28 %   arXiv:2402.08593 table 4
  GIN                       33.09 %   arXiv:2306.16424 table 2
  PNA                       38.29 %   arXiv:2306.16424 table 2
  GIN+EU                    39.27 %   arXiv:2306.16424 table 2

The GRAPH feature block below re-implements the Graph Feature Preprocessor idea
(fan-in/fan-out, cycles, scatter-gather, per-vertex amount statistics) in DuckDB,
because snapml has no wheel for the Python in this repo.

Causality: every graph feature for a transaction at time t is computed from
transactions strictly before t. Rolling windows end one minute before t and the
cycle features only count structure whose edges all first appeared before t.

Usage:
  python scripts/benchmark_edge_level.py
  python scripts/benchmark_edge_level.py --window-days 7 --degree-cap 200
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_recall_curve

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/processed/aml.duckdb"
DEFAULT_REPORT = ROOT / "reports/edge-benchmark/benchmark.json"

# Published reference points, for the comparison block in the report.
PUBLISHED_LI_SMALL_F1 = {
    "xgboost_basic_features": 0.0021,
    "lightgbm_basic_features": 0.0205,
    "mlp": 0.1459,
    "lightgbm_plus_gfp": 0.2083,
    "xgboost_plus_gfp": 0.2728,
    "gin": 0.3309,
    "pna": 0.3829,
    "gin_plus_eu": 0.3927,
}

# docs/ml/FIN-07-ML-002 bans these two outright: Payment Format carries a 6.4x
# (LI-Small) to 7.6x (HI-Medium) laundering lift, and hour-of-day is a generator
# artifact on LI-Small. They stay in BASIC_FEATURES so our numbers remain
# comparable to the papers, which do use them, but the policy_compliant arm drops
# them so the cost of obeying the ban is measured rather than assumed.
EDA_BANNED_FEATURES = ["channel_code", "hour_of_day"]

BASIC_FEATURES = [
    "log_amount",
    "log_amount_received",
    "amount_conversion_ratio",
    "cross_bank",
    "cross_currency",
    "channel_code",
    "hour_of_day",
    "day_of_week",
]

GRAPH_FEATURES = [
    # per-vertex activity and amount statistics (GFP "vertex statistics")
    "a_out_cnt_7d",
    "a_out_sum_7d",
    "a_out_max_7d",
    "a_in_cnt_7d",
    "a_in_sum_7d",
    "a_in_max_7d",
    "b_in_cnt_7d",
    "b_in_sum_7d",
    "b_in_max_7d",
    "b_out_cnt_7d",
    "b_out_sum_7d",
    # short-horizon flow, for pass-through / layering
    "a_in_cnt_24h",
    "a_in_sum_24h",
    "a_max_in_24h",
    "a_mins_since_last_in",
    "b_out_cnt_24h",
    # GFP single-hop patterns
    "fan_in_b",
    "fan_out_a",
    # whether this exact counterparty pair is transacting for the first time —
    # empirically stronger than the cumulative counterparty count
    "is_new_pair",
    # GFP multi-hop patterns
    "n_2cycle",
    "n_3cycle",
    "gather_scatter_a",
    "gather_scatter_b",
    # amount-conservation ratios (the typology signature)
    "passthrough_ratio_24h",
    "amount_match_24h",
    "balance_ratio_7d",
    # explicit "the denominator was zero" signals, replacing the old blown-up ratios
    "a_no_inflow_24h",
    "a_no_inflow_7d",
]

# Only used when --forward-hours > 0, i.e. when the run declares a detection lag.
# These describe what happened AFTER the transaction, which is information a bank
# genuinely has if it alerts hours or days later instead of in real time.
FORWARD_FEATURES = [
    "b_out_cnt_fwd",
    "b_out_sum_fwd",
    "b_in_cnt_fwd",
    "a_out_cnt_fwd",
    "b_mins_to_next_out",
    "fwd_conservation",
    "fwd_amount_match",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument(
        "--degree-cap",
        type=int,
        default=200,
        help="Skip triangle intermediates above this degree; 15 hub accounts "
        "otherwise dominate the 2-path enumeration.",
    )
    p.add_argument(
        "--forward-hours",
        type=int,
        default=0,
        help="Detection lag in hours. 0 keeps the strictly causal setup. When >0, "
        "features may also describe what happened up to this many hours AFTER the "
        "transaction, which is what a bank has if it alerts with a delay.",
    )
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--memory-limit", default="6GB")
    return p.parse_args()


def build_features(
    con: duckdb.DuckDBPyConnection, window_days: int, degree_cap: int, forward_hours: int = 24
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per transaction, with strictly causal graph features.

    Returns (features, split_summary). Only the model columns cross into pandas;
    ids and timestamps stay in DuckDB so the frame fits in memory on big files.
    """
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE degrees AS
        SELECT acct, count(*) AS total FROM (
            SELECT to_account_key AS acct FROM transaction
            UNION ALL SELECT from_account_key FROM transaction
        ) GROUP BY 1
        """
    )
    # Distinct directed account pairs, with the first time each pair transacted.
    # Cycle features may only use a pair once that first timestamp has passed.
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pairs AS
        SELECT from_account_key AS s, to_account_key AS d, min(occurred_at) AS first_ts
        FROM transaction
        WHERE from_account_key IS NOT NULL AND to_account_key IS NOT NULL
        GROUP BY 1, 2
        """
    )
    # Triangles B -> C -> A, keyed by the (A, B) edge that would close them.
    # ready_ts is when BOTH legs exist, so the count is causal.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE triangles AS
        SELECT p2.s AS b, p3.d AS a,
               greatest(p2.first_ts, p3.first_ts) AS ready_ts,
               count(*) AS n
        FROM pairs p2
        JOIN degrees dc ON dc.acct = p2.d AND dc.total <= {int(degree_cap)}
        JOIN pairs p3 ON p3.s = p2.d
        WHERE p3.d <> p2.s
        GROUP BY 1, 2, 3
        """
    )
    # Cumulative distinct-counterparty counts used to live here, joined ASOF.
    # They were dropped: the two ASOF joins re-sorted all 29M rows and exhausted
    # the temp directory on HI-Medium, and on LI-Small the cumulative count
    # measured weaker than the is_new_pair flag that replaced it.
    #
    # Rolling per-account activity at (account, minute) grain. Both windows end
    # one minute BEFORE the current row, so a transaction never sees itself or
    # anything simultaneous.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE rolled AS
        WITH events AS (
            SELECT from_account_key AS acct, occurred_at AS ts, 0.0 AS in_amt, amount AS out_amt
            FROM transaction WHERE from_account_key IS NOT NULL
            UNION ALL
            SELECT to_account_key, occurred_at, amount, 0.0
            FROM transaction WHERE to_account_key IS NOT NULL
        ),
        per_minute AS (
            SELECT acct, ts,
                   count(*) FILTER (WHERE in_amt > 0)  AS in_cnt,
                   count(*) FILTER (WHERE out_amt > 0) AS out_cnt,
                   sum(in_amt) AS in_sum, sum(out_amt) AS out_sum,
                   max(in_amt) AS in_max, max(out_amt) AS out_max
            FROM events GROUP BY 1, 2
        )
        SELECT acct, ts,
            coalesce(sum(in_cnt)  OVER w_long, 0)   AS in_cnt_7d,
            coalesce(sum(in_sum)  OVER w_long, 0.0) AS in_sum_7d,
            coalesce(max(in_max)  OVER w_long, 0.0) AS in_max_7d,
            coalesce(sum(out_cnt) OVER w_long, 0)   AS out_cnt_7d,
            coalesce(sum(out_sum) OVER w_long, 0.0) AS out_sum_7d,
            coalesce(max(out_max) OVER w_long, 0.0) AS out_max_7d,
            coalesce(sum(in_cnt)  OVER w_day, 0)    AS in_cnt_24h,
            coalesce(sum(in_sum)  OVER w_day, 0.0)  AS in_sum_24h,
            coalesce(max(in_max)  OVER w_day, 0.0)  AS max_in_24h,
            coalesce(sum(out_cnt) OVER w_day, 0)    AS out_cnt_24h,
            max(CASE WHEN in_cnt > 0 THEN ts END) OVER w_long AS last_in_ts,
            -- Forward window: what the account does AFTER this moment. Only legal
            -- because the run declares a detection lag (--forward-hours); the
            -- alert is raised at t + lag, so this data is already history by then.
            coalesce(sum(out_cnt) OVER w_fwd, 0)    AS out_cnt_fwd,
            coalesce(sum(out_sum) OVER w_fwd, 0.0)  AS out_sum_fwd,
            coalesce(max(out_max) OVER w_fwd, 0.0)  AS out_max_fwd,
            coalesce(sum(in_cnt)  OVER w_fwd, 0)    AS in_cnt_fwd,
            min(CASE WHEN out_cnt > 0 THEN ts END) OVER w_fwd AS next_out_ts
        FROM per_minute
        WINDOW
          w_long AS (PARTITION BY acct ORDER BY ts
                     RANGE BETWEEN INTERVAL {int(window_days)} DAY PRECEDING
                                AND INTERVAL 1 MINUTE PRECEDING),
          w_fwd  AS (PARTITION BY acct ORDER BY ts
                     RANGE BETWEEN INTERVAL 1 MINUTE FOLLOWING
                                AND INTERVAL {max(int(forward_hours), 1)} HOUR FOLLOWING),
          w_day  AS (PARTITION BY acct ORDER BY ts
                     RANGE BETWEEN INTERVAL 24 HOUR PRECEDING
                                AND INTERVAL 1 MINUTE PRECEDING)
        """
    )
    # Materialise in stages. A single mega-query made DuckDB sort the whole wide
    # table twice and spill tens of GB to disk on HI-Medium (29M rows).
    # The 60/20/20 boundary is taken as two timestamps rather than by numbering
    # every row. row_number() OVER (ORDER BY ...) is a global sort of the whole
    # wide table and did not finish in 10 minutes on HI-Medium's 29M rows.
    # Timestamps are minute-granular, so a whole minute lands on one side of a
    # cut; with millions of rows per split the proportions barely move.
    cut_60, cut_80 = con.execute(
        "SELECT quantile_disc(occurred_at, 0.6), quantile_disc(occurred_at, 0.8) FROM transaction"
    ).fetchone()
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE edge_base AS
        SELECT transaction_id, occurred_at, from_account_key, to_account_key,
               from_bank, to_bank, payment_currency, receiving_currency, channel,
               amount, amount_received, amount_paid_orig, label_laundering,
               CASE WHEN occurred_at <= $cut60 THEN 'train'
                    WHEN occurred_at <= $cut80 THEN 'val' ELSE 'test' END AS split
        FROM transaction
        """,
        {"cut60": cut_60, "cut80": cut_80},
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE two_cycle AS
        SELECT t1.transaction_id AS tx, count(*) AS n
        FROM transaction t1
        JOIN transaction t2
          ON t2.from_account_key = t1.to_account_key
         AND t2.to_account_key = t1.from_account_key
         AND t2.occurred_at < t1.occurred_at
         AND t2.occurred_at >= t1.occurred_at - INTERVAL {int(window_days)} DAY
        GROUP BY 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE three_cycle AS
        SELECT o.transaction_id AS tx, coalesce(sum(tri.n), 0) AS n
        FROM edge_base o
        JOIN triangles tri
          ON tri.b = o.to_account_key AND tri.a = o.from_account_key
         AND tri.ready_ts < o.occurred_at
        GROUP BY 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE features AS
        SELECT
            o.occurred_at,
            o.split,
            o.from_account_key,
            o.to_account_key,
            o.amount_paid_orig,
            o.label_laundering::TINYINT AS y,

            ln(1 + o.amount) AS log_amount,
            ln(1 + o.amount_received) AS log_amount_received,
            o.amount_received / (o.amount + 1e-9) AS amount_conversion_ratio,
            (o.from_bank <> o.to_bank)::TINYINT AS cross_bank,
            (o.payment_currency <> o.receiving_currency)::TINYINT AS cross_currency,
            (hash(o.channel) % 64)::DOUBLE AS channel_code,
            extract(hour FROM o.occurred_at)::DOUBLE AS hour_of_day,
            extract(dow FROM o.occurred_at)::DOUBLE AS day_of_week,

            coalesce(a.out_cnt_7d, 0)::DOUBLE AS a_out_cnt_7d,
            coalesce(a.out_sum_7d, 0.0) AS a_out_sum_7d,
            coalesce(a.out_max_7d, 0.0) AS a_out_max_7d,
            coalesce(a.in_cnt_7d, 0)::DOUBLE AS a_in_cnt_7d,
            coalesce(a.in_sum_7d, 0.0) AS a_in_sum_7d,
            coalesce(a.in_max_7d, 0.0) AS a_in_max_7d,
            coalesce(b.in_cnt_7d, 0)::DOUBLE AS b_in_cnt_7d,
            coalesce(b.in_sum_7d, 0.0) AS b_in_sum_7d,
            coalesce(b.in_max_7d, 0.0) AS b_in_max_7d,
            coalesce(b.out_cnt_7d, 0)::DOUBLE AS b_out_cnt_7d,
            coalesce(b.out_sum_7d, 0.0) AS b_out_sum_7d,

            coalesce(a.in_cnt_24h, 0)::DOUBLE AS a_in_cnt_24h,
            coalesce(a.in_sum_24h, 0.0) AS a_in_sum_24h,
            coalesce(a.max_in_24h, 0.0) AS a_max_in_24h,
            coalesce(date_diff('minute', a.last_in_ts, o.occurred_at), 99999)::DOUBLE
                AS a_mins_since_last_in,
            coalesce(b.out_cnt_24h, 0)::DOUBLE AS b_out_cnt_24h,

            coalesce(b.in_cnt_7d, 0)::DOUBLE AS fan_in_b,
            coalesce(a.out_cnt_7d, 0)::DOUBLE AS fan_out_a,
            (pr.first_ts = o.occurred_at)::TINYINT AS is_new_pair,

            coalesce(c2.n, 0)::DOUBLE AS n_2cycle,
            coalesce(c3.n, 0)::DOUBLE AS n_3cycle,
            coalesce(a.in_cnt_7d, 0)::DOUBLE * coalesce(a.out_cnt_7d, 0) AS gather_scatter_a,
            coalesce(b.in_cnt_7d, 0)::DOUBLE * coalesce(b.out_cnt_7d, 0) AS gather_scatter_b,

            -- Ratios are only defined when the denominator is real. Previously these
            -- divided by (denom + 1e-9), so a zero denominator produced values in the
            -- trillions and the model learned "denominator was zero" the long way round.
            -- Now the zero case is its own explicit flag and the ratio is capped.
            CASE WHEN coalesce(a.in_sum_24h, 0.0) > 0
                 THEN least(o.amount / a.in_sum_24h, 1e6) ELSE 0.0 END AS passthrough_ratio_24h,
            (coalesce(a.in_sum_24h, 0.0) = 0)::TINYINT AS a_no_inflow_24h,
            CASE WHEN coalesce(a.max_in_24h, 0.0) > 0
                 THEN least(o.amount / a.max_in_24h, 1e6) ELSE 0.0 END AS amount_match_24h,
            CASE WHEN coalesce(a.in_sum_7d, 0.0) > 0
                 THEN least(a.out_sum_7d / a.in_sum_7d, 1e6) ELSE 0.0 END AS balance_ratio_7d,
            (coalesce(a.in_sum_7d, 0.0) = 0)::TINYINT AS a_no_inflow_7d,

            -- Forward-looking block: does the receiver pass the money straight on?
            coalesce(b.out_cnt_fwd, 0)::DOUBLE AS b_out_cnt_fwd,
            coalesce(b.out_sum_fwd, 0.0) AS b_out_sum_fwd,
            coalesce(b.in_cnt_fwd, 0)::DOUBLE AS b_in_cnt_fwd,
            coalesce(a.out_cnt_fwd, 0)::DOUBLE AS a_out_cnt_fwd,
            coalesce(date_diff('minute', o.occurred_at, b.next_out_ts), 99999)::DOUBLE
                AS b_mins_to_next_out,
            -- how much of what B just received leaves again inside the lag window.
            -- Capped: amounts run down to 6.7e-5 USD, so an uncapped ratio reaches 1e14.
            least(coalesce(b.out_sum_fwd, 0.0) / (o.amount + 1e-9), 1e6) AS fwd_conservation,
            -- does one single outgoing transfer nearly match what B received
            least(coalesce(b.out_max_fwd, 0.0) / (o.amount + 1e-9), 1e6) AS fwd_amount_match
        FROM edge_base o
        LEFT JOIN rolled a ON a.acct = o.from_account_key AND a.ts = o.occurred_at
        LEFT JOIN rolled b ON b.acct = o.to_account_key   AND b.ts = o.occurred_at
        LEFT JOIN two_cycle c2 ON c2.tx = o.transaction_id
        LEFT JOIN three_cycle c3 ON c3.tx = o.transaction_id
        LEFT JOIN pairs pr
          ON pr.s = o.from_account_key AND pr.d = o.to_account_key
        """
    )
    # Split boundaries come from SQL so occurred_at never has to enter pandas.
    summary = con.execute(
        """
        SELECT split, count(*) AS rows, sum(y) AS laundering,
               min(occurred_at) AS start, max(occurred_at) AS "end"
        FROM features GROUP BY 1
        """
    ).fetchdf()
    columns = ", ".join(f'"{name}"' for name in BASIC_FEATURES + GRAPH_FEATURES + FORWARD_FEATURES)
    frame = con.execute(f"SELECT split, y, {columns} FROM features").fetchdf()
    return frame, summary


class DataQualityError(RuntimeError):
    """Raised when the input or the built features are not fit to train on."""


def run_data_quality(con: duckdb.DuckDBPyConnection, frame: pd.DataFrame, features: list[str]) -> dict:
    """Check the source table and the built feature matrix before any training.

    The previous version of this script quietly replaced inf/NaN with zero. That
    hides exactly the failures worth knowing about, so the counts are reported and
    a hard failure stops the run.
    """
    report: dict = {"hard_failures": [], "warnings": [], "metrics": {}}

    source = (
        con.execute(
            """
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE occurred_at IS NULL) AS null_ts,
               count(*) FILTER (WHERE from_account_key IS NULL
                             OR to_account_key IS NULL) AS null_account,
               count(*) FILTER (WHERE amount IS NULL) AS null_amount,
               count(*) FILTER (WHERE amount <= 0) AS non_positive_amount,
               count(*) FILTER (WHERE from_account_key = to_account_key) AS self_loops,
               count(*) FILTER (WHERE label_laundering NOT IN (0, 1)) AS bad_label,
               count(DISTINCT transaction_id) AS distinct_ids
        FROM transaction
        """
        )
        .fetchdf()
        .iloc[0]
    )
    report["metrics"]["source"] = {k: int(v) for k, v in source.items()}

    for column in ("null_ts", "null_account", "null_amount", "bad_label", "self_loops"):
        if int(source[column]) > 0:
            report["hard_failures"].append(f"{column}={int(source[column])}")
    if int(source["distinct_ids"]) != int(source["rows"]):
        report["hard_failures"].append(f"duplicate transaction_id: {int(source['rows']) - int(source['distinct_ids'])}")
    if int(source["non_positive_amount"]) > 0:
        # Not fatal on its own, but every amount feature is a log or a ratio.
        report["warnings"].append(f"non_positive_amount={int(source['non_positive_amount'])}")

    values = frame[features].to_numpy(dtype=np.float64, copy=False)
    n_nan = int(np.isnan(values).sum())
    n_inf = int(np.isinf(values).sum())
    report["metrics"]["features"] = {
        "rows": int(len(frame)),
        "columns": len(features),
        "nan_cells": n_nan,
        "inf_cells": n_inf,
        "cells": int(values.size),
    }
    # A handful of non-finite cells is a feature-definition slip; a large share means
    # the matrix is not describing what it claims to.
    if values.size and (n_nan + n_inf) / values.size > 1e-4:
        report["hard_failures"].append(f"non-finite cells {(n_nan + n_inf):,} exceed 0.01% of the matrix")
    elif n_nan or n_inf:
        report["warnings"].append(f"non-finite cells: nan={n_nan:,} inf={n_inf:,}")

    extreme = {
        name: int(np.isfinite(col).sum() and (np.abs(col[np.isfinite(col)]) > 1e12).sum())
        for name, col in ((f, frame[f].to_numpy(dtype=np.float64, copy=False)) for f in features)
    }
    blown = {k: v for k, v in extreme.items() if v}
    if blown:
        report["warnings"].append(f"features with |value| > 1e12: {blown}")
    report["metrics"]["features"]["blown_up"] = blown

    for split in ("train", "val", "test"):
        part = frame[frame.split == split]
        if part.empty:
            report["hard_failures"].append(f"split {split} is empty")
        elif int(part.y.sum()) == 0:
            report["hard_failures"].append(f"split {split} has no positive labels")

    report["ok"] = not report["hard_failures"]
    return report


def confusion(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((y == 1) & (pred == 1)).sum())
    fn = int(((y == 1) & (pred == 0)).sum())
    fp = int(((y == 0) & (pred == 1)).sum())
    tn = int(((y == 0) & (pred == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "caught_true_positive": tp,
        "missed_false_negative": fn,
        "false_alarm_false_positive": fp,
        "correctly_ignored_true_negative": tn,
        "alerts_raised": tp + fp,
        "real_cases_in_period": tp + fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "alerts_per_real_case": round((tp + fp) / (tp + fn), 1) if tp + fn else None,
    }


def best_f1_threshold(y: np.ndarray, score: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y, score)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    # precision_recall_curve returns one more point than thresholds.
    return float(thresholds[int(np.argmax(f1[:-1]))])


# Searched on validation only. Test is touched once, after the winner is frozen.
MODEL_GRID = [
    {"max_iter": 200, "max_leaf_nodes": 31, "learning_rate": 0.1, "class_weight": "balanced"},
    {"max_iter": 500, "max_leaf_nodes": 63, "learning_rate": 0.05, "class_weight": "balanced"},
    {"max_iter": 500, "max_leaf_nodes": 63, "learning_rate": 0.05, "class_weight": None},
    {"max_iter": 800, "max_leaf_nodes": 127, "learning_rate": 0.05, "class_weight": None},
]


SEEDS = (42, 1, 2, 3, 4)


def _fit(config: dict, features: list[str], train: pd.DataFrame, seed: int = 42) -> HistGradientBoostingClassifier:
    model = HistGradientBoostingClassifier(
        learning_rate=config["learning_rate"],
        max_iter=config["max_iter"],
        max_leaf_nodes=config["max_leaf_nodes"],
        min_samples_leaf=50,
        l2_regularization=1.0,
        class_weight=config["class_weight"],
        early_stopping=False,
        random_state=seed,
    )
    model.fit(train[features].to_numpy(dtype=np.float32), train.y.to_numpy())
    return model


def evaluate(name: str, features: list[str], frames: dict[str, pd.DataFrame]) -> dict:
    train, val, test = frames["train"], frames["val"], frames["test"]
    y_val = val.y.to_numpy()
    started = time.perf_counter()

    best = None
    trials = []
    for config in MODEL_GRID:
        model = _fit(config, features, train)
        val_score = model.predict_proba(val[features].to_numpy(dtype=np.float32))[:, 1]
        threshold = best_f1_threshold(y_val, val_score)
        val_result = confusion(y_val, (val_score >= threshold).astype(int))
        trials.append({"config": config, "validation_f1": val_result["f1"]})
        if best is None or val_result["f1"] > best["val_result"]["f1"]:
            best = {
                "config": config,
                "model": model,
                "threshold": threshold,
                "val_result": val_result,
            }

    # The papers report mean +/- std over repeated runs; with only a few hundred
    # positives in test, a single seed is not a trustworthy number.
    y_test = test.y.to_numpy()
    test_matrix = test[features].to_numpy(dtype=np.float32)
    val_matrix = val[features].to_numpy(dtype=np.float32)
    seed_results = []
    for seed in SEEDS:
        model = best["model"] if seed == 42 else _fit(best["config"], features, train, seed)
        threshold = best_f1_threshold(y_val, model.predict_proba(val_matrix)[:, 1])
        score = model.predict_proba(test_matrix)[:, 1]
        seed_results.append(
            {
                "seed": seed,
                "threshold": round(threshold, 6),
                **confusion(y_test, (score >= threshold).astype(int)),
                "pr_auc": round(float(average_precision_score(y_test, score)), 6),
            }
        )
    f1_values = np.array([r["f1"] for r in seed_results])

    # F1 picks one conservative operating point. An AML team usually wants to
    # see the trade-off, so report what each alert budget buys.
    test_score = best["model"].predict_proba(test_matrix)[:, 1]
    order = np.argsort(-test_score, kind="mergesort")
    total_positive = int(y_test.sum())
    operating_points = []
    for budget in (100, 250, 500, 1000, 2500, 5000, 12239):
        if budget > len(y_test):
            continue
        caught = int(y_test[order[:budget]].sum())
        operating_points.append(
            {
                "alerts_reviewed": budget,
                "caught": caught,
                "missed": total_positive - caught,
                "false_alarms": budget - caught,
                "precision": round(caught / budget, 4),
                "recall": round(caught / total_positive, 4),
            }
        )

    result = {
        "feature_set": name,
        "n_features": len(features),
        "selected_config": best["config"],
        "validation_grid": trials,
        "threshold_from_validation": round(best["threshold"], 6),
        "validation": best["val_result"],
        "test": confusion(y_test, (test_score >= best["threshold"]).astype(int)),
        "test_pr_auc": round(float(average_precision_score(y_test, test_score)), 6),
        "test_operating_points": operating_points,
        "test_f1_over_seeds": {
            "mean": round(float(f1_values.mean()), 6),
            "std": round(float(f1_values.std()), 6),
            "runs": seed_results,
        },
        "fit_seconds": round(time.perf_counter() - started, 1),
    }
    t = result["test"]
    print(
        f"  {name:22s} F1={t['f1']:.4f}  P={t['precision']:.4f}  R={t['recall']:.4f}  "
        f"caught={t['caught_true_positive']}  missed={t['missed_false_negative']}  "
        f"false_alarms={t['false_alarm_false_positive']:,}",
        flush=True,
    )
    return result


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    print("[1/5] Building edge features (this reads the whole transaction table) ...", flush=True)
    con = duckdb.connect(str(args.db), read_only=True)
    con.execute("SET TimeZone='UTC'")
    con.execute(f"SET threads={int(args.threads)}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    # Row order carries no meaning here; keeping it forces DuckDB to buffer whole
    # sorted results and was the difference between running and a 30 GB spill.
    con.execute("SET preserve_insertion_order=false")
    all_features = BASIC_FEATURES + GRAPH_FEATURES + FORWARD_FEATURES
    try:
        expected_rows = con.execute("SELECT count(*) FROM transaction").fetchone()[0]
        frame, summary = build_features(con, args.window_days, args.degree_cap, max(args.forward_hours, 24))
        if len(frame) != expected_rows:
            raise DataQualityError(
                f"feature build changed the row count: {len(frame):,} rows from "
                f"{expected_rows:,} transactions — a join is fanning out"
            )
        print("[2/5] Data quality gate ...", flush=True)
        dq = run_data_quality(con, frame, all_features)
    finally:
        con.close()
    for warning in dq["warnings"]:
        print(f"      [warn] {warning}", flush=True)
    if not dq["ok"]:
        raise DataQualityError("; ".join(dq["hard_failures"]))
    print("      passed", flush=True)

    # float32 halves peak memory; the estimator casts to float32 at fit time anyway.
    # On HI-Medium (31.9M rows) float64 would need roughly 9 GB for this frame alone.
    frame[all_features] = frame[all_features].astype(np.float32).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    frames = {name: frame[frame.split == name] for name in ("train", "val", "test")}

    print("[3/5] Split summary", flush=True)
    summary = summary.set_index("split")
    split_counts = {}
    for name, part in frames.items():
        row = summary.loc[name]
        split_counts[name] = {
            "rows": int(row["rows"]),
            "laundering": int(row["laundering"]),
            "illicit_ratio": round(float(row["laundering"]) / float(row["rows"]), 8),
            "start": row["start"].isoformat(),
            "end": row["end"].isoformat(),
        }
        print(
            f"  {name:5s} {len(part):>10,} rows  {int(part.y.sum()):>6,} laundering  "
            f"1 in {int(1 / part.y.mean()) if part.y.mean() else 0:,}",
            flush=True,
        )

    print("[4/5] Training and evaluating", flush=True)
    causal_features = BASIC_FEATURES + GRAPH_FEATURES
    policy_features = [name for name in causal_features if name not in EDA_BANNED_FEATURES]
    arms = [
        ("basic_only", BASIC_FEATURES),
        ("basic_plus_graph", causal_features),
        # Same model, minus the two features the team EDA bans. The gap between this
        # and basic_plus_graph is how much of the score rides on Payment Format.
        ("policy_compliant", policy_features),
    ]
    if args.forward_hours > 0:
        arms.append(("plus_forward_window", all_features))

    # Each arm takes tens of minutes on HI-Medium. Write the report after every one
    # so an interrupted run keeps the arms that already finished instead of losing
    # every metric that was computed but not yet persisted.
    results: list[dict] = []
    for arm_name, arm_features in arms:
        results.append(evaluate(arm_name, arm_features, frames))
        write_report(args, split_counts, dq, results, started, partial=len(results) < len(arms))

    print("[5/5] Complete", flush=True)
    return 0


def write_report(
    args: argparse.Namespace,
    split_counts: dict,
    dq: dict,
    results: list[dict],
    started: float,
    *,
    partial: bool,
) -> None:
    report = {
        "partial": partial,
        "schema_version": "fin07.edge_benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": {
            "unit": "transaction (edge classification)",
            "split": "60/20/20 temporal on transactions ordered by timestamp",
            "metric": "minority-class F1; threshold maximises F1 on validation",
            "causality": "graph windows end 1 minute before the scored transaction; "
            "cycle features only count structure whose edges predate it",
            "window_days": args.window_days,
            "degree_cap_for_triangles": args.degree_cap,
            "model": "sklearn HistGradientBoostingClassifier (LightGBM-equivalent; "
            "snapml/LightGBM/XGBoost unavailable for this Python)",
            "source_papers": [
                "Altman et al., NeurIPS 2023 D&B, arXiv:2306.16424",
                "Blanusa et al., ICAIF 2024, arXiv:2402.08593",
            ],
        },
        "split_counts": split_counts,
        "data_quality": dq,
        "results": results,
        "published_li_small_f1_for_reference": PUBLISHED_LI_SMALL_F1,
        "runtime": {
            "python": platform.python_version(),
            "duckdb": duckdb.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "seconds": round(time.perf_counter() - started, 1),
        },
    }
    args.report_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    state = "partial" if partial else "final"
    print(f"      report ({state}, {len(results)} arms) -> {args.report_out}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
