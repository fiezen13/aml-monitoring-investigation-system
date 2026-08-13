"""Build account dimension from cleaned transactions."""

from __future__ import annotations

import pandas as pd

from src.data.schemas import ACCOUNT_COLUMNS


def build_accounts(transactions: pd.DataFrame) -> pd.DataFrame:
    """Union of from/to accounts with activity stats (graph nodes, not KYC)."""
    if transactions.empty:
        return pd.DataFrame(columns=list(ACCOUNT_COLUMNS))

    outgoing = (
        transactions.groupby("from_account_key", sort=False)
        .agg(
            bank_id=("from_bank", "first"),
            account_raw=("from_account_raw", "first"),
            first_seen_at=("occurred_at", "min"),
            last_seen_at=("occurred_at", "max"),
            tx_count_out=("transaction_id", "count"),
        )
        .reset_index()
        .rename(columns={"from_account_key": "account_key"})
    )
    incoming = (
        transactions.groupby("to_account_key", sort=False)
        .agg(
            bank_id=("to_bank", "first"),
            account_raw=("to_account_raw", "first"),
            first_seen_at=("occurred_at", "min"),
            last_seen_at=("occurred_at", "max"),
            tx_count_in=("transaction_id", "count"),
        )
        .reset_index()
        .rename(columns={"to_account_key": "account_key"})
    )

    accounts = outgoing.merge(incoming, on="account_key", how="outer", suffixes=("_out", "_in"))
    accounts["bank_id"] = accounts["bank_id_out"].fillna(accounts["bank_id_in"])
    accounts["account_raw"] = accounts["account_raw_out"].fillna(accounts["account_raw_in"])
    accounts["first_seen_at"] = accounts[["first_seen_at_out", "first_seen_at_in"]].min(axis=1)
    accounts["last_seen_at"] = accounts[["last_seen_at_out", "last_seen_at_in"]].max(axis=1)
    accounts["tx_count_out"] = accounts["tx_count_out"].fillna(0).astype("int64")
    accounts["tx_count_in"] = accounts["tx_count_in"].fillna(0).astype("int64")

    # Prefer bank/raw from outgoing when both present
    out = accounts[list(ACCOUNT_COLUMNS)].sort_values("account_key", kind="mergesort").reset_index(drop=True)
    return out
