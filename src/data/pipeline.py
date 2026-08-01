"""Orchestrate FIN-07 Task 1 ETL end-to-end."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.build_accounts import build_accounts
from src.data.dq import run_dq, write_dq_report
from src.data.etl_transactions import read_raw_transactions, transform_transactions
from src.data.load_duckdb import load_to_duckdb
from src.data.split import assign_time_split, write_split_cutoffs


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def dataframe_checksum(df: pd.DataFrame) -> str:
    """Stable checksum for reproducibility tests."""
    payload = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_task1_etl(
    raw_path: str | Path,
    db_path: str | Path,
    *,
    seed: int = 42,
    report_dir: str | Path | None = None,
    strict_li_small_stats: bool = False,
) -> dict:
    """
    Single-command Task 1 pipeline:
    raw CSV → transaction + account → DQ → DuckDB (indexed).
    """
    set_seed(seed)
    raw_path = Path(raw_path)
    db_path = Path(db_path)
    report_dir = Path(report_dir) if report_dir else db_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    raw = read_raw_transactions(raw_path)
    tx, etl_stats = transform_transactions(raw)
    tx, cutoffs = assign_time_split(tx)
    accounts = build_accounts(tx)

    dq_report = run_dq(
        tx,
        accounts,
        etl_stats,
        strict_li_small_stats=strict_li_small_stats,
    )
    dq_report["checksums"] = {
        "transaction": dataframe_checksum(tx),
        "account": dataframe_checksum(accounts),
    }
    dq_report["seed"] = seed

    load_to_duckdb(tx, accounts, db_path)
    write_dq_report(dq_report, report_dir / "dq_report.json")
    write_split_cutoffs(cutoffs, report_dir / "split_cutoffs.json")

    return {
        "db_path": str(db_path),
        "n_transactions": len(tx),
        "n_accounts": len(accounts),
        "dq_report": dq_report,
        "split_cutoffs": cutoffs,
    }
