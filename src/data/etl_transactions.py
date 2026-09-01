"""Extract / transform IBM LI-Small transactions (FIN-07 DAT §4.1)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.currency import to_usd
from src.data.schemas import (
    COMMON_CURRENCY,
    RAW_COLUMNS,
    make_account_key,
    normalize_channel,
)


def _stable_transaction_id(row: pd.Series) -> str:
    payload = "|".join(
        [
            str(row["occurred_at"]),
            str(row["from_account_key"]),
            str(row["to_account_key"]),
            f"{row['amount_paid_orig']:.10f}",
            str(row["payment_currency"]),
            f"{row['amount_received_orig']:.10f}",
            str(row["receiving_currency"]),
            str(row["channel"]),
            str(row["_row_ord"]),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def read_raw_transactions(path: str | Path) -> pd.DataFrame:
    """Read raw CSV; fail if columns missing (no silent column loss)."""
    df = pd.read_csv(path)
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Raw file missing columns: {missing}; got {list(df.columns)}")
    return df[RAW_COLUMNS].copy()


def transform_transactions(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Map IBM columns → FIN-07 transaction schema.
    Returns (clean_df, stats) where stats includes n_raw and n_self_loops.
    """
    n_raw = len(raw)
    df = pd.DataFrame(
        {
            "occurred_at": pd.to_datetime(raw["Timestamp"], utc=True),
            "from_bank": raw["From Bank"],
            "from_account_raw": raw["Account"].astype(str),
            "to_bank": raw["To Bank"],
            "to_account_raw": raw["Account.1"].astype(str),
            "amount_paid_orig": pd.to_numeric(raw["Amount Paid"], errors="raise"),
            "payment_currency": raw["Payment Currency"].astype(str),
            "amount_received_orig": pd.to_numeric(raw["Amount Received"], errors="raise"),
            "receiving_currency": raw["Receiving Currency"].astype(str),
            "channel": raw["Payment Format"].map(normalize_channel),
            "label_laundering": pd.to_numeric(raw["Is Laundering"], errors="raise").fillna(0).astype(np.int8),
        }
    )
    df["from_account_key"] = [
        make_account_key(b, a) for b, a in zip(df["from_bank"], df["from_account_raw"], strict=True)
    ]
    df["to_account_key"] = [make_account_key(b, a) for b, a in zip(df["to_bank"], df["to_account_raw"], strict=True)]

    self_loop_mask = (df["from_account_key"] == df["to_account_key"]).to_numpy()
    n_self_loops = int(self_loop_mask.sum())
    paid_all = pd.to_numeric(raw["Amount Paid"], errors="raise").to_numpy(dtype=float)
    recv_all = pd.to_numeric(raw["Amount Received"], errors="raise").to_numpy(dtype=float)

    df = df.loc[~self_loop_mask].copy()

    df["amount"] = [to_usd(a, c) for a, c in zip(df["amount_paid_orig"], df["payment_currency"], strict=True)]
    df["amount_received"] = [
        to_usd(a, c) for a, c in zip(df["amount_received_orig"], df["receiving_currency"], strict=True)
    ]
    df["currency"] = COMMON_CURRENCY

    # Stable order for deterministic IDs when payloads collide
    df = df.sort_values(
        ["occurred_at", "from_account_key", "to_account_key", "amount_paid_orig"],
        kind="mergesort",
    ).reset_index(drop=True)
    df["_row_ord"] = np.arange(len(df), dtype=np.int64)
    df["transaction_id"] = df.apply(_stable_transaction_id, axis=1)
    df = df.drop(columns=["_row_ord"])

    stats = {
        "n_raw": n_raw,
        "n_self_loops": n_self_loops,
        "n_loaded": len(df),
        "sum_amount_paid_orig": float(df["amount_paid_orig"].sum()) if len(df) else 0.0,
        "sum_amount_received_orig": float(df["amount_received_orig"].sum()) if len(df) else 0.0,
        "sum_amount_paid_raw_all": float(paid_all.sum()),
        "sum_amount_received_raw_all": float(recv_all.sum()),
        "sum_amount_paid_self_loops": float(paid_all[self_loop_mask].sum()) if n_self_loops else 0.0,
        "sum_amount_received_self_loops": float(recv_all[self_loop_mask].sum()) if n_self_loops else 0.0,
    }
    return df, stats
