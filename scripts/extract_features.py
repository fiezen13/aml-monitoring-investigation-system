"""Trích 20 đặc trưng hành vi tài khoản từ DuckDB theo docs/feature_spec.md.

Ví dụ:
  python scripts/extract_features.py
  python scripts/extract_features.py --window 7d
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import polars as pl

DB_PATH = Path("data/processed/aml.duckdb")
PROCESSED_DIR = Path("data/processed")
SPLITS = ("train", "val", "test")
EPS = 1e-6

WINDOW_DAYS = {"1d": 1, "7d": 7, "14d": 14}

FEATURE_COLS = [
    "txn_count",
    "incoming_count",
    "outgoing_count",
    "active_days",
    "txn_per_active_day",
    "total_inflow",
    "total_outflow",
    "net_flow",
    "outflow_inflow_ratio",
    "rapid_outflow_ratio",
    "median_dwell_time",
    "unique_in_counterparties",
    "unique_out_counterparties",
    "new_counterparty_ratio",
    "median_amount",
    "p90_amount",
    "amount_std",
    "near_threshold_ratio",
    "off_hour_ratio",
    "median_inter_txn_gap",
]

RATIO_COLS = [
    "txn_per_active_day",
    "outflow_inflow_ratio",
    "rapid_outflow_ratio",
    "new_counterparty_ratio",
    "near_threshold_ratio",
    "off_hour_ratio",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract 20 account features from aml.duckdb")
    p.add_argument("--window", default="7d", choices=tuple(WINDOW_DAYS))
    p.add_argument("--db", default=str(DB_PATH), help="Duong dan DuckDB")
    return p.parse_args()


def _load_split_tx(con: duckdb.DuckDBPyConnection, split: str) -> pl.DataFrame:
    """Doc transaction theo split — KHONG lay label_laundering (anti-leakage)."""
    rel = con.execute(
        """
        SELECT
            occurred_at,
            from_account_key,
            to_account_key,
            CAST(amount AS DOUBLE) AS amount
        FROM transaction
        WHERE split = ?
          AND from_account_key IS NOT NULL
          AND to_account_key IS NOT NULL
          AND amount IS NOT NULL
          AND occurred_at IS NOT NULL
        """,
        [split],
    )
    try:
        arrow = rel.to_arrow_table()
    except AttributeError:
        arrow = rel.fetch_arrow_table()
    df = pl.from_arrow(arrow)
    df = df.with_columns(pl.col("occurred_at").dt.convert_time_zone("UTC"))
    return df


def _to_events(tx: pl.DataFrame) -> pl.DataFrame:
    credit = tx.select(
        pl.col("occurred_at").alias("ts"),
        pl.col("to_account_key").alias("account_key"),
        pl.col("from_account_key").alias("counterparty"),
        pl.col("amount"),
        pl.lit("in").alias("direction"),
    )
    debit = tx.select(
        pl.col("occurred_at").alias("ts"),
        pl.col("from_account_key").alias("account_key"),
        pl.col("to_account_key").alias("counterparty"),
        pl.col("amount"),
        pl.lit("out").alias("direction"),
    )
    return pl.concat([credit, debit], how="vertical")


def _pass_through_features(win_events: pl.DataFrame) -> pl.DataFrame:
    empty = pl.DataFrame(
        schema={
            "account_key": pl.Utf8,
            "rapid_outflow_ratio": pl.Float64,
            "median_dwell_time": pl.Float64,
        }
    )
    if win_events.is_empty():
        return empty

    ins = (
        win_events.filter(pl.col("direction") == "in")
        .select("account_key", pl.col("ts").alias("in_ts"), pl.col("amount").alias("in_amt"))
        .sort(["account_key", "in_ts"])
    )
    outs = (
        win_events.filter(pl.col("direction") == "out")
        .select("account_key", pl.col("ts").alias("out_ts"), pl.col("amount").alias("out_amt"))
        .sort(["account_key", "out_ts"])
    )

    accounts = win_events.select("account_key").unique()

    if outs.is_empty():
        rapid = accounts.with_columns(pl.lit(0.0).alias("rapid_outflow_ratio"))
    else:
        joined = outs.join_asof(
            ins.select("account_key", "in_ts"),
            left_on="out_ts",
            right_on="in_ts",
            by="account_key",
            strategy="backward",
        ).with_columns(
            (
                pl.col("in_ts").is_not_null()
                & ((pl.col("out_ts") - pl.col("in_ts")).dt.total_seconds() >= 0)
                & ((pl.col("out_ts") - pl.col("in_ts")).dt.total_seconds() <= 2 * 3600)
            ).alias("is_rapid")
        )
        rapid = joined.group_by("account_key").agg(
            (
                pl.col("out_amt").filter(pl.col("is_rapid")).sum().fill_null(0.0)
                / (pl.col("out_amt").sum() + EPS)
            ).alias("rapid_outflow_ratio")
        )

    if ins.is_empty() or outs.is_empty():
        dwell = accounts.with_columns(pl.lit(999.0).alias("median_dwell_time"))
    else:
        pairs = ins.join_asof(
            outs.select("account_key", "out_ts"),
            left_on="in_ts",
            right_on="out_ts",
            by="account_key",
            strategy="forward",
        ).with_columns(
            ((pl.col("out_ts") - pl.col("in_ts")).dt.total_seconds() / 3600.0).alias("dwell_h")
        )
        dwell = pairs.group_by("account_key").agg(
            pl.col("dwell_h").drop_nulls().median().alias("median_dwell_time")
        ).with_columns(pl.col("median_dwell_time").fill_null(999.0))

    return rapid.join(dwell, on="account_key", how="full", coalesce=True).with_columns(
        [
            pl.col("rapid_outflow_ratio").fill_null(0.0),
            pl.col("median_dwell_time").fill_null(999.0),
        ]
    )


def _new_counterparty_ratio(win_events: pl.DataFrame, hist_events: pl.DataFrame) -> pl.DataFrame:
    if hist_events.is_empty():
        return win_events.select("account_key").unique().with_columns(
            pl.lit(1.0).alias("new_counterparty_ratio")
        )
    win_cp = win_events.select("account_key", "counterparty").unique()
    hist_cp = hist_events.select("account_key", "counterparty").unique().with_columns(
        pl.lit(True).alias("seen_before")
    )
    marked = win_cp.join(hist_cp, on=["account_key", "counterparty"], how="left")
    return marked.group_by("account_key").agg(
        (
            pl.col("seen_before").is_null().sum().cast(pl.Float64)
            / (pl.len().cast(pl.Float64) + EPS)
        ).alias("new_counterparty_ratio")
    )


def _inter_txn_gap(win_events: pl.DataFrame) -> pl.DataFrame:
    return (
        win_events.sort(["account_key", "ts"])
        .with_columns(
            (pl.col("ts").diff().over("account_key").dt.total_seconds() / 60.0).alias("gap_min")
        )
        .group_by("account_key")
        .agg(pl.col("gap_min").drop_nulls().median().alias("median_inter_txn_gap"))
        .with_columns(pl.col("median_inter_txn_gap").fill_null(99999.0))
    )


def extract_split_features(tx: pl.DataFrame, window: str) -> pl.DataFrame:
    """Snapshot / account: as_of = EOD UTC cua ngay giao dich cuoi trong split."""
    days = WINDOW_DAYS[window]
    events = _to_events(tx).sort(["account_key", "ts"])

    # as_of_ts = end-of-day (UTC) cua ngay last-activity tung account
    # window: (as_of - window, as_of]  — tuong duong lookback tu last activity
    events = events.with_columns(pl.col("ts").max().over("account_key").alias("acc_max_ts"))

    # Gan as_of = acc_max_ts (diem neo); EOD chi dung de ghi metadata
    # Dung lookback truc tiep tu acc_max_ts de tranh lech timezone EOD
    win_events = events.filter(
        (pl.col("ts") > pl.col("acc_max_ts") - pl.duration(days=days))
        & (pl.col("ts") <= pl.col("acc_max_ts"))
    )
    hist_events = events.filter(pl.col("ts") <= pl.col("acc_max_ts") - pl.duration(days=days))

    # Fallback 1.1: chi account co >= 1 TX trong window (groupby tu win_events)
    if win_events.is_empty():
        return pl.DataFrame(
            schema={
                "account_key": pl.Utf8,
                "as_of_ts": pl.Datetime(time_unit="us", time_zone="UTC"),
                "window": pl.Utf8,
                **{c: pl.Float64 for c in FEATURE_COLS},
            }
        )

    # as_of_ts metadata: EOD UTC cua ngay acc_max
    as_of_map = (
        win_events.select("account_key", "acc_max_ts")
        .unique(subset=["account_key"])
        .with_columns(
            # ceil toi cuoi ngay UTC cua acc_max_ts
            (
                pl.col("acc_max_ts").dt.truncate("1d")
                + pl.duration(days=1)
                - pl.duration(seconds=1)
            ).alias("as_of_ts")
        )
        .select("account_key", "as_of_ts")
    )

    win_events = win_events.with_columns(
        [
            (pl.col("direction") == "in").alias("is_in"),
            (pl.col("direction") == "out").alias("is_out"),
            ((pl.col("amount") >= 9000) & (pl.col("amount") < 10000)).alias("is_near"),
            pl.col("ts").dt.hour().is_in([0, 1, 2, 3, 4, 5]).alias("is_off"),
            pl.col("ts").dt.date().alias("day"),
        ]
    )

    base = win_events.group_by("account_key").agg(
        [
            pl.len().alias("txn_count"),
            pl.col("is_in").sum().alias("incoming_count"),
            pl.col("is_out").sum().alias("outgoing_count"),
            pl.col("day").n_unique().alias("active_days"),
            pl.col("amount").filter(pl.col("is_in")).sum().fill_null(0.0).alias("sum_in"),
            pl.col("amount").filter(pl.col("is_out")).sum().fill_null(0.0).alias("sum_out"),
            pl.col("counterparty")
            .filter(pl.col("is_in"))
            .n_unique()
            .alias("unique_in_counterparties"),
            pl.col("counterparty")
            .filter(pl.col("is_out"))
            .n_unique()
            .alias("unique_out_counterparties"),
            pl.col("amount").median().alias("median_amount_raw"),
            pl.col("amount").quantile(0.90).alias("p90_amount_raw"),
            pl.col("amount").std().alias("amount_std_raw"),
            (pl.col("is_near").sum() / (pl.len() + EPS)).alias("near_threshold_ratio"),
            (pl.col("is_off").sum() / (pl.len() + EPS)).alias("off_hour_ratio"),
        ]
    )

    base = base.with_columns(
        [
            (pl.col("txn_count") / (pl.col("active_days") + EPS)).alias("txn_per_active_day"),
            (pl.col("sum_out") / (pl.col("sum_in") + EPS)).alias("outflow_inflow_ratio"),
            # Fallback 1.3 heavy-tail: log1p
            (pl.col("sum_in") + 1.0).log().alias("total_inflow"),
            (pl.col("sum_out") + 1.0).log().alias("total_outflow"),
            (
                pl.when(pl.col("sum_in") - pl.col("sum_out") >= 0)
                .then(1.0)
                .otherwise(-1.0)
                * (1.0 + (pl.col("sum_in") - pl.col("sum_out")).abs()).log()
            ).alias("net_flow"),
            (1.0 + pl.col("median_amount_raw").fill_null(0.0)).log().alias("median_amount"),
            (1.0 + pl.col("p90_amount_raw").fill_null(0.0)).log().alias("p90_amount"),
            (1.0 + pl.col("amount_std_raw").fill_null(0.0)).log().alias("amount_std"),
        ]
    )

    pt = _pass_through_features(win_events)
    ncp = _new_counterparty_ratio(win_events, hist_events)
    gaps = _inter_txn_gap(win_events)

    feats = (
        base.join(pt, on="account_key", how="left")
        .join(ncp, on="account_key", how="left")
        .join(gaps, on="account_key", how="left")
        .join(as_of_map, on="account_key", how="left")
        .with_columns(pl.lit(window).alias("window"))
    )

    # Fallback 1.2
    feats = feats.with_columns(
        [pl.col(c).fill_null(0.0).fill_nan(0.0) for c in RATIO_COLS]
        + [
            pl.col("median_dwell_time").fill_null(999.0),
            pl.col("median_inter_txn_gap").fill_null(99999.0),
            pl.col("unique_in_counterparties").fill_null(0).cast(pl.Int64),
            pl.col("unique_out_counterparties").fill_null(0).cast(pl.Int64),
            pl.col("txn_count").cast(pl.Int64),
            pl.col("incoming_count").cast(pl.Int64),
            pl.col("outgoing_count").cast(pl.Int64),
            pl.col("active_days").cast(pl.Int64),
        ]
    )

    return feats.select(["account_key", "as_of_ts", "window", *FEATURE_COLS]).sort("account_key")


def extract_features(window: str, db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Khong tim thay DuckDB: {db_path}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)

    try:
        for split in SPLITS:
            print(f"[{split}] Doc transaction tu DuckDB (khong lay label_laundering)...")
            tx = _load_split_tx(con, split)
            if tx.is_empty():
                raise RuntimeError(f"Split '{split}' rong trong bang transaction.")

            print(f"[{split}] rows={tx.height:,} | window={window}")
            feats = extract_split_features(tx, window=window)
            out = PROCESSED_DIR / f"features_{split}_{window}.parquet"
            feats.write_parquet(out, compression="zstd")
            print(f"[{split}] -> {out} | accounts={feats.height:,} | cols={feats.width}")
    finally:
        con.close()

    print(f"DONE: features_{{train,val,test}}_{window}.parquet")


def main() -> None:
    args = _parse_args()
    extract_features(args.window, Path(args.db))


if __name__ == "__main__":
    main()
