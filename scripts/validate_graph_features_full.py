#!/usr/bin/env python3
"""Validate graph_features_v1.parquet via DuckDB (no full pandas load)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.graph_features import OUTPUT_COLUMNS  # noqa: E402
from src.data.snapshot_split import (  # noqa: E402
    assign_snapshot_split,
    load_split_cutoffs,
    parse_utc,
    snapshot_window_bounds,
)

FEATURE8 = (
    "in_degree_7d",
    "out_degree_7d",
    "unique_neighbors_7d",
    "in_out_degree_ratio_7d",
    "new_in_counterparty_ratio_7d",
    "new_out_counterparty_ratio_7d",
    "inflow_concentration_7d",
    "outflow_dispersion_7d",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parquet",
        type=Path,
        default=ROOT / "data/processed/graph_features_v1.parquet",
    )
    parser.add_argument(
        "--cutoffs",
        type=Path,
        default=ROOT / "data/processed/split_cutoffs.json",
    )
    parser.add_argument("--db", type=Path, default=ROOT / "data/processed/aml.duckdb")
    args = parser.parse_args()
    pq = args.parquet.resolve().as_posix()
    cutoffs = load_split_cutoffs(args.cutoffs)
    con = duckdb.connect()

    issues: list[str] = []

    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{pq}')").fetchall()]
    if cols != list(OUTPUT_COLUMNS):
        issues.append(f"column mismatch: {cols}")
    if any(c.startswith("label_") for c in cols):
        issues.append("label_* present")

    n_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{pq}')").fetchone()[0]
    n_snap = con.execute(
        f"SELECT COUNT(DISTINCT snapshot_date) FROM read_parquet('{pq}')"
    ).fetchone()[0]
    snaps = [
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT snapshot_date FROM read_parquet('{pq}') ORDER BY 1"
        ).fetchall()
    ]
    splits = dict(
        con.execute(
            f"SELECT sample_split, COUNT(*) FROM read_parquet('{pq}') GROUP BY 1 ORDER BY 1"
        ).fetchall()
    )
    dup = con.execute(
        f"""
        SELECT COUNT(*) FROM (
          SELECT account_key, as_of_ts, "window", COUNT(*) AS c
          FROM read_parquet('{pq}')
          GROUP BY 1,2,3
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    null_inf = {}
    for col in OUTPUT_COLUMNS:
        col_sql = f'"{col}"' if col == "window" else col
        if col in ("account_key", "window", "sample_split", "feature_schema_version", "snapshot_date", "as_of_ts"):
            n_null = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{pq}') WHERE {col_sql} IS NULL"
            ).fetchone()[0]
            null_inf[col] = {"null": n_null}
        else:
            q = f"""
            SELECT
              SUM(CASE WHEN {col_sql} IS NULL THEN 1 ELSE 0 END) AS n_null,
              SUM(CASE WHEN isinf({col_sql}::DOUBLE) THEN 1 ELSE 0 END) AS n_inf,
              SUM(CASE WHEN isnan({col_sql}::DOUBLE) THEN 1 ELSE 0 END) AS n_nan
            FROM read_parquet('{pq}')
            """
            n_null, n_inf, n_nan = con.execute(q).fetchone()
            null_inf[col] = {"null": n_null, "inf": n_inf, "nan": n_nan}
            if n_null or n_inf or n_nan:
                issues.append(f"{col} null/inf/nan={null_inf[col]}")

    if dup:
        issues.append(f"duplicate PK groups: {dup}")

    # ranges
    bad_hist = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{pq}') WHERE history_available NOT IN (0,1)"
    ).fetchone()[0]
    if bad_hist:
        issues.append(f"invalid history_available: {bad_hist}")
    bad_split = con.execute(
        f"""
        SELECT COUNT(*) FROM read_parquet('{pq}')
        WHERE sample_split NOT IN ('train','val','test')
        """
    ).fetchone()[0]
    if bad_split:
        issues.append(f"invalid sample_split: {bad_split}")

    for col, lo, hi in (
        ("in_out_degree_ratio_7d", -1.0, 1.0),
        ("new_in_counterparty_ratio_7d", 0.0, 1.0),
        ("new_out_counterparty_ratio_7d", 0.0, 1.0),
        ("inflow_concentration_7d", 0.0, 1.0),
        ("outflow_dispersion_7d", 0.0, 1.0),
    ):
        n_bad = con.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{pq}')
            WHERE {col} < {lo} - 1e-9 OR {col} > {hi} + 1e-9
            """
        ).fetchone()[0]
        if n_bad:
            issues.append(f"{col} out of [{lo},{hi}]: {n_bad}")

    # as_of / split consistency per snapshot
    for snap in snaps:
        d = snap if hasattr(snap, "year") else snap
        _s, end_ts = snapshot_window_bounds(d)
        expected = assign_snapshot_split(end_ts, cutoffs)
        row = con.execute(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE as_of_ts != ?::TIMESTAMPTZ) AS bad_asof,
              COUNT(*) FILTER (WHERE sample_split != ?) AS bad_split
            FROM read_parquet('{pq}')
            WHERE snapshot_date = ?
            """,
            [end_ts.to_pydatetime(), expected, d],
        ).fetchone()
        if row[0]:
            issues.append(f"as_of mismatch D={d}: {row[0]}")
        if row[1]:
            issues.append(f"split mismatch D={d}: {row[1]} expected={expected}")

    mm = {}
    for col in FEATURE8:
        mn, mx = con.execute(
            f"SELECT MIN({col}), MAX({col}) FROM read_parquet('{pq}')"
        ).fetchone()
        mm[col] = {"min": mn, "max": mx}

    hist_dist = dict(
        con.execute(
            f"""
            SELECT history_available, COUNT(*)
            FROM read_parquet('{pq}') GROUP BY 1 ORDER BY 1
            """
        ).fetchall()
    )
    hist_days = con.execute(
        f"SELECT MIN(history_days_observed), MAX(history_days_observed) FROM read_parquet('{pq}')"
    ).fetchone()

    # deterministic summary checksum over sorted PK + key features
    digest_src = con.execute(
        f"""
        SELECT
          COUNT(*)::VARCHAR || '|' ||
          COALESCE(SUM(in_degree_7d),0)::VARCHAR || '|' ||
          COALESCE(SUM(out_degree_7d),0)::VARCHAR || '|' ||
          COALESCE(SUM(unique_neighbors_7d),0)::VARCHAR || '|' ||
          COALESCE(ROUND(SUM(in_out_degree_ratio_7d)::DOUBLE, 6),0)::VARCHAR || '|' ||
          COALESCE(ROUND(SUM(new_in_counterparty_ratio_7d)::DOUBLE, 6),0)::VARCHAR || '|' ||
          COALESCE(ROUND(SUM(new_out_counterparty_ratio_7d)::DOUBLE, 6),0)::VARCHAR || '|' ||
          COALESCE(ROUND(SUM(inflow_concentration_7d)::DOUBLE, 6),0)::VARCHAR || '|' ||
          COALESCE(ROUND(SUM(outflow_dispersion_7d)::DOUBLE, 6),0)::VARCHAR || '|' ||
          COALESCE(SUM(history_available),0)::VARCHAR || '|' ||
          COALESCE(SUM(history_days_observed),0)::VARCHAR
        FROM read_parquet('{pq}')
        """
    ).fetchone()[0]
    checksum = hashlib.sha256(digest_src.encode()).hexdigest()[:16]

    n_tx = None
    if args.db.exists():
        con.execute(f"ATTACH '{args.db.resolve().as_posix()}' AS aml (READ_ONLY)")
        n_tx = con.execute("SELECT COUNT(*) FROM aml.transaction").fetchone()[0]

    print("=== full artifact summary ===")
    print(f"parquet={args.parquet} size_MB={args.parquet.stat().st_size/1024/1024:.2f}")
    print(f"input_tx={n_tx}")
    print(f"output_rows={n_rows}")
    print(f"snapshot_count={n_snap}")
    print(f"snapshot_dates={snaps}")
    print(f"sample_split={splits}")
    print(f"duplicate_pk_groups={dup}")
    print(f"history_available={hist_dist}")
    print(f"history_days_observed min/max={hist_days}")
    print(f"feature_minmax={json.dumps(mm, default=str)}")
    print(f"null_inf={json.dumps(null_inf)}")
    print(f"checksum16={checksum} digest_src={digest_src}")

    print("\n=== sample rows by split ===")
    for split in ("train", "val", "test"):
        rows = con.execute(
            f"""
            SELECT account_key, as_of_ts, snapshot_date, sample_split,
                   in_degree_7d, out_degree_7d, unique_neighbors_7d,
                   in_out_degree_ratio_7d, new_in_counterparty_ratio_7d,
                   new_out_counterparty_ratio_7d, inflow_concentration_7d,
                   outflow_dispersion_7d, history_available, history_days_observed
            FROM read_parquet('{pq}')
            WHERE sample_split = ?
            ORDER BY as_of_ts, account_key
            LIMIT 5
            """,
            [split],
        ).fetchdf()
        print(f"\n-- {split} --")
        print(rows.to_string(index=False) if len(rows) else "(none)")

    # boundary checks
    print("\n=== split boundary as_of ===")
    train_end = parse_utc(cutoffs["train_end_ts"])
    val_end = parse_utc(cutoffs["val_end_ts"])
    as_ofs = [
        parse_utc(r[0])
        for r in con.execute(
            f"SELECT DISTINCT as_of_ts FROM read_parquet('{pq}') ORDER BY 1"
        ).fetchall()
    ]
    for label, cut in (("train_end", train_end), ("val_end", val_end)):
        before = [t for t in as_ofs if t <= cut]
        after = [t for t in as_ofs if t > cut]
        for name, t in (("last_le", before[-1] if before else None), ("first_gt", after[0] if after else None)):
            if t is None:
                print(f"  {label}/{name}: none")
                continue
            expected = assign_snapshot_split(t, cutoffs)
            actual = con.execute(
                f"""
                SELECT DISTINCT sample_split FROM read_parquet('{pq}')
                WHERE as_of_ts = ?::TIMESTAMPTZ
                """,
                [t.to_pydatetime()],
            ).fetchall()
            actual_l = [a[0] for a in actual]
            ok = actual_l == [expected]
            print(f"  {label}/{name}: as_of={t} expected={expected} actual={actual_l} {'OK' if ok else 'FAIL'}")
            if not ok:
                issues.append(f"boundary {label}/{name}")

    print("\n=== validation ===")
    if issues:
        for x in issues:
            print(f"FAIL: {x}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
