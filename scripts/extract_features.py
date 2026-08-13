"""Trích 20 đặc trưng hành vi tài khoản từ DuckDB theo docs/feature_spec.md.

Ví dụ:
  python scripts/extract_features.py
  python scripts/extract_features.py --window 7d
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
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
    "repeated_amount_ratio",
    "median_inter_txn_gap",
    "p10_inter_txn_gap",
]

RATIO_COLS = [
    "txn_per_active_day",
    "outflow_inflow_ratio",
    "rapid_outflow_ratio",
    "new_counterparty_ratio",
    "repeated_amount_ratio",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract 20 account features from aml.duckdb")
    p.add_argument("--window", default="7d", choices=tuple(WINDOW_DAYS))
    p.add_argument("--db", default=str(DB_PATH), help="Duong dan DuckDB")
    p.add_argument("--output-dir", default=str(PROCESSED_DIR), help="Thu muc ghi feature parquet")
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
            (pl.col("out_amt").filter(pl.col("is_rapid")).sum().fill_null(0.0) / (pl.col("out_amt").sum() + EPS)).alias(
                "rapid_outflow_ratio"
            )
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
        ).with_columns(((pl.col("out_ts") - pl.col("in_ts")).dt.total_seconds() / 3600.0).alias("dwell_h"))
        dwell = (
            pairs.group_by("account_key")
            .agg(pl.col("dwell_h").drop_nulls().median().alias("median_dwell_time"))
            .with_columns(pl.col("median_dwell_time").fill_null(999.0))
        )

    return rapid.join(dwell, on="account_key", how="full", coalesce=True).with_columns(
        [
            pl.col("rapid_outflow_ratio").fill_null(0.0),
            pl.col("median_dwell_time").fill_null(999.0),
        ]
    )


def _new_counterparty_ratio(win_events: pl.DataFrame, hist_events: pl.DataFrame) -> pl.DataFrame:
    if hist_events.is_empty():
        return win_events.select("account_key").unique().with_columns(pl.lit(1.0).alias("new_counterparty_ratio"))
    win_cp = win_events.select("account_key", "counterparty").unique()
    hist_cp = hist_events.select("account_key", "counterparty").unique().with_columns(pl.lit(True).alias("seen_before"))
    marked = win_cp.join(hist_cp, on=["account_key", "counterparty"], how="left")
    return marked.group_by("account_key").agg(
        (pl.col("seen_before").is_null().sum().cast(pl.Float64) / (pl.len().cast(pl.Float64) + EPS)).alias(
            "new_counterparty_ratio"
        )
    )


def _inter_txn_gap(win_events: pl.DataFrame) -> pl.DataFrame:
    """median + p10 khoang cach lien tiep (phut)."""
    return (
        win_events.sort(["account_key", "ts"])
        .with_columns((pl.col("ts").diff().over("account_key").dt.total_seconds() / 60.0).alias("gap_min"))
        .group_by("account_key")
        .agg(
            [
                pl.col("gap_min").drop_nulls().median().alias("median_inter_txn_gap"),
                pl.col("gap_min").drop_nulls().quantile(0.10).alias("p10_inter_txn_gap"),
            ]
        )
        .with_columns(
            [
                pl.col("median_inter_txn_gap").fill_null(99999.0),
                pl.col("p10_inter_txn_gap").fill_null(99999.0),
            ]
        )
    )


def _repeated_amount_ratio(win_events: pl.DataFrame) -> pl.DataFrame:
    """Ty le TX co amount xuat hien >= 2 lan trong window (smurfing)."""
    amt_freq = win_events.group_by(["account_key", "amount"]).agg(pl.len().alias("amt_n"))
    tagged = win_events.join(amt_freq, on=["account_key", "amount"], how="left")
    return tagged.group_by("account_key").agg(
        ((pl.col("amt_n") >= 2).sum() / (pl.len() + EPS)).alias("repeated_amount_ratio")
    )


def _empty_feature_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "account_key": pl.Utf8,
            "as_of_ts": pl.Datetime(time_unit="us", time_zone="UTC"),
            "window": pl.Utf8,
            **{c: pl.Float64 for c in FEATURE_COLS},
        }
    )


def _aggregate_account_features(win_events: pl.DataFrame, hist_events: pl.DataFrame) -> pl.DataFrame:
    """Tinh 20 feature cho moi account co >= 1 TX trong window (handoff §3.3.4)."""
    win_events = win_events.with_columns(
        [
            (pl.col("direction") == "in").alias("is_in"),
            (pl.col("direction") == "out").alias("is_out"),
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
            pl.col("counterparty").filter(pl.col("is_in")).n_unique().alias("unique_in_counterparties"),
            pl.col("counterparty").filter(pl.col("is_out")).n_unique().alias("unique_out_counterparties"),
            pl.col("amount").median().alias("median_amount_raw"),
            pl.col("amount").quantile(0.90).alias("p90_amount_raw"),
            pl.col("amount").std().alias("amount_std_raw"),
        ]
    )

    base = base.with_columns(
        [
            (pl.col("txn_count") / (pl.col("active_days") + EPS)).alias("txn_per_active_day"),
            (pl.col("sum_out") / (pl.col("sum_in") + EPS)).alias("outflow_inflow_ratio"),
            (pl.col("sum_in") + 1.0).log().alias("total_inflow"),
            (pl.col("sum_out") + 1.0).log().alias("total_outflow"),
            (
                pl.when(pl.col("sum_in") - pl.col("sum_out") >= 0).then(1.0).otherwise(-1.0)
                * (1.0 + (pl.col("sum_in") - pl.col("sum_out")).abs()).log()
            ).alias("net_flow"),
            (1.0 + pl.col("median_amount_raw").fill_null(0.0)).log().alias("median_amount"),
            (1.0 + pl.col("p90_amount_raw").fill_null(0.0)).log().alias("p90_amount"),
            (1.0 + pl.col("amount_std_raw").fill_null(0.0)).log().alias("amount_std"),
        ]
    )

    feats = (
        base.join(_pass_through_features(win_events), on="account_key", how="left")
        .join(_new_counterparty_ratio(win_events, hist_events), on="account_key", how="left")
        .join(_inter_txn_gap(win_events), on="account_key", how="left")
        .join(_repeated_amount_ratio(win_events), on="account_key", how="left")
    )

    return feats.with_columns(
        [pl.col(c).fill_null(0.0).fill_nan(0.0) for c in RATIO_COLS]
        + [
            pl.col("median_dwell_time").fill_null(999.0),
            pl.col("median_inter_txn_gap").fill_null(99999.0),
            pl.col("p10_inter_txn_gap").fill_null(99999.0),
            pl.col("unique_in_counterparties").fill_null(0).cast(pl.Int64),
            pl.col("unique_out_counterparties").fill_null(0).cast(pl.Int64),
            pl.col("txn_count").cast(pl.Int64),
            pl.col("incoming_count").cast(pl.Int64),
            pl.col("outgoing_count").cast(pl.Int64),
            pl.col("active_days").cast(pl.Int64),
        ]
    )


def extract_split_features(tx: pl.DataFrame, window: str) -> pl.DataFrame:
    """Daily EOD UTC snapshots — handoff §3.3.

    Moi ngay lich D: as_of_ts = 23:59:59Z; feature tu
    (as_of_ts - window, as_of_ts]; chi account co >= 1 TX trong window.
    """
    days = WINDOW_DAYS[window]
    events = _to_events(tx).sort(["account_key", "ts"])
    if events.is_empty():
        return _empty_feature_frame()

    ts_min = events.select(pl.col("ts").min()).item()
    ts_max = events.select(pl.col("ts").max()).item()
    day_start = ts_min.date()
    day_end = ts_max.date()
    n_days = (day_end - day_start).days + 1
    print(
        f"       daily EOD: {day_start} -> {day_end} ({n_days} ngay, window={window})",
        flush=True,
    )

    frames: list[pl.DataFrame] = []
    d = day_start
    day_i = 0
    while d <= day_end:
        day_i += 1
        as_of = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=UTC)
        win_start = as_of - timedelta(days=days)

        win_events = events.filter((pl.col("ts") > pl.lit(win_start)) & (pl.col("ts") <= pl.lit(as_of)))
        if win_events.is_empty():
            d += timedelta(days=1)
            continue

        hist_events = events.filter(pl.col("ts") <= pl.lit(win_start))
        day_feats = _aggregate_account_features(win_events, hist_events)
        day_feats = day_feats.with_columns(
            [
                pl.lit(as_of).cast(pl.Datetime(time_unit="us", time_zone="UTC")).alias("as_of_ts"),
                pl.lit(window).alias("window"),
            ]
        )
        frames.append(day_feats.select(["account_key", "as_of_ts", "window", *FEATURE_COLS]))

        if day_i == 1 or day_i == n_days or day_i % 5 == 0:
            print(
                f"       [{day_i}/{n_days}] {d} accounts={day_feats.height:,}",
                flush=True,
            )
        d += timedelta(days=1)

    if not frames:
        return _empty_feature_frame()

    return pl.concat(frames, how="vertical").sort(["as_of_ts", "account_key"])


def extract_features(window: str, db_path: Path, output_dir: Path = PROCESSED_DIR) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Khong tim thay DuckDB: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)

    try:
        for split in SPLITS:
            print(f"[{split}] Doc transaction tu DuckDB (khong lay label_laundering)...")
            tx = _load_split_tx(con, split)
            if tx.is_empty():
                raise RuntimeError(f"Split '{split}' rong trong bang transaction.")

            print(f"[{split}] rows={tx.height:,} | window={window}")
            feats = extract_split_features(tx, window=window)
            out = output_dir / f"features_{split}_{window}.parquet"
            feats.write_parquet(out, compression="zstd")
            print(f"[{split}] -> {out} | samples={feats.height:,} | cols={feats.width}")
    finally:
        con.close()

    print(f"DONE: features_{{train,val,test}}_{window}.parquet")


def main() -> None:
    args = _parse_args()
    extract_features(args.window, Path(args.db), Path(args.output_dir))


if __name__ == "__main__":
    main()
