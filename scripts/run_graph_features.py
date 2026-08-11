#!/usr/bin/env python3
"""Build graph_features_v1.parquet from Task 1 DuckDB (features only).

Uses DuckDB COPY → parquet (no full pandas materialization).
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from datetime import timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.graph_features import export_graph_features_from_duckdb  # noqa: E402
from src.data.snapshot_split import load_split_cutoffs  # noqa: E402


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 Graph features v1")
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "data/processed/aml.duckdb",
        help="Task 1 DuckDB path",
    )
    parser.add_argument(
        "--cutoffs",
        type=Path,
        default=ROOT / "data/processed/split_cutoffs.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data/processed/graph_features_v1.parquet",
    )
    parser.add_argument("--start", default=None, help="Optional UTC date YYYY-MM-DD")
    parser.add_argument("--end-exclusive", default=None, help="Optional UTC date YYYY-MM-DD")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"DuckDB not found: {args.db}", file=sys.stderr)
        return 1
    if not args.cutoffs.exists():
        print(f"Cutoffs not found: {args.cutoffs}", file=sys.stderr)
        return 1

    from datetime import datetime

    range_start = (
        datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc) if args.start else None
    )
    range_end = (
        datetime.fromisoformat(args.end_exclusive).replace(tzinfo=timezone.utc)
        if args.end_exclusive
        else None
    )
    cutoffs = load_split_cutoffs(args.cutoffs)

    print(f"rss_before_MB={rss_mb():.1f}", flush=True)
    t0 = time.perf_counter()
    meta = export_graph_features_from_duckdb(
        args.db,
        cutoffs,
        args.out,
        range_start=range_start,
        range_end_exclusive=range_end,
    )
    elapsed = time.perf_counter() - t0
    print(f"rss_after_MB={rss_mb():.1f}", flush=True)
    print(f"runtime_s={elapsed:.2f}", flush=True)
    print(json.dumps(meta, default=str), flush=True)

    con = duckdb.connect()
    pq = Path(args.out).resolve().as_posix()
    splits = con.execute(
        f"SELECT sample_split, COUNT(*) AS n FROM read_parquet('{pq}') GROUP BY 1 ORDER BY 1"
    ).fetchall()
    con.close()
    print(f"OK: {meta['n_rows']} rows → {args.out} ({elapsed:.2f}s); splits={dict(splits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
