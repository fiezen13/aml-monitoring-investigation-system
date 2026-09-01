"""Load transaction / account tables into DuckDB (indexes after bulk load)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.data.schemas import ACCOUNT_COLUMNS, TRANSACTION_ALL_COLUMNS


def load_to_duckdb(
    transactions: pd.DataFrame,
    accounts: pd.DataFrame,
    db_path: str | Path,
) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    tx = transactions.loc[:, list(TRANSACTION_ALL_COLUMNS)].copy()
    acct = accounts.loc[:, list(ACCOUNT_COLUMNS)].copy()

    con = duckdb.connect(str(db_path))
    try:
        con.register("tx_df", tx)
        con.register("acct_df", acct)

        con.execute("CREATE TABLE transaction AS SELECT * FROM tx_df")
        con.execute("CREATE TABLE account AS SELECT * FROM acct_df")

        # Indexes AFTER bulk load (RD5)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_pk ON transaction(transaction_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_occurred ON transaction(occurred_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_from ON transaction(from_account_key)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_to ON transaction(to_account_key)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_from_time ON transaction(from_account_key, occurred_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_to_time ON transaction(to_account_key, occurred_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_split ON transaction(split)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_acct_pk ON account(account_key)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_acct_bank ON account(bank_id)")
    finally:
        con.close()
