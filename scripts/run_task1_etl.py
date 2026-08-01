#!/usr/bin/env python3
"""Run FIN-07 Task 1: load & normalize IBM LI-Small → DuckDB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/run_task1_etl.py` from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.pipeline import run_task1_etl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 Task 1 ETL (LI-Small → DuckDB)")
    parser.add_argument(
        "--raw",
        type=Path,
        default=ROOT / "data/raw/ibm_li_small/LI-Small_Trans.csv",
        help="Path to LI-Small transactions CSV",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "data/processed/aml.duckdb",
        help="Output DuckDB path",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory for dq_report.json and split_cutoffs.json",
    )
    parser.add_argument(
        "--strict-li-small-stats",
        action="store_true",
        help="Fail if account count / laundering rate outside LI-Small bands",
    )
    args = parser.parse_args()

    if not args.raw.exists():
        print(f"Raw file not found: {args.raw}", file=sys.stderr)
        print(
            "Download IBM LI-Small from Kaggle "
            "(ealtman2019/ibm-transactions-for-anti-money-laundering-aml) "
            "and place LI-Small_Trans.csv under data/raw/ibm_li_small/",
            file=sys.stderr,
        )
        return 1

    result = run_task1_etl(
        args.raw,
        args.db,
        seed=args.seed,
        report_dir=args.report_dir,
        strict_li_small_stats=args.strict_li_small_stats,
    )
    print(
        f"OK: {result['n_transactions']} transactions, "
        f"{result['n_accounts']} accounts → {result['db_path']}"
    )
    warnings = result["dq_report"].get("warnings") or []
    for w in warnings:
        print(f"WARNING: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
