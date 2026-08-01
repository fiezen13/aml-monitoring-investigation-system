"""Time-based train/val/test split (60/20/20) — FIN-07 ND2 / DAT §4.2."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def assign_time_split(
    transactions: pd.DataFrame,
    train_ratio: float = 0.60,
    val_ratio: float = 0.20,
) -> tuple[pd.DataFrame, dict]:
    """
    Sort by (occurred_at, transaction_id), cut by row position for ~60/20/20.
    Guarantees max(train) < min(val) and max(val) < min(test) on timestamps
    when boundary timestamps are not shared across splits; if a timestamp
    sits on a cut, the entire timestamp group stays in the earlier split.
    """
    if not 0 < train_ratio < 1 or not 0 < val_ratio < 1 or train_ratio + val_ratio >= 1:
        raise ValueError("Invalid split ratios")

    df = transactions.sort_values(["occurred_at", "transaction_id"], kind="mergesort").reset_index(
        drop=True
    )
    n = len(df)
    if n == 0:
        df["split"] = pd.Series(dtype=str)
        return df, {"train_end_ts": None, "val_end_ts": None, "n": 0}

    train_cut = int(n * train_ratio)
    val_cut = int(n * (train_ratio + val_ratio))
    train_cut = max(1, min(train_cut, n - 2)) if n >= 3 else max(0, n - 2)
    val_cut = max(train_cut + 1, min(val_cut, n - 1)) if n >= 3 else max(train_cut + 1, n - 1)

    # Expand cuts so all rows sharing the boundary timestamp stay in earlier split
    train_cut = _expand_cut_exclusive(df, train_cut)
    val_cut = _expand_cut_exclusive(df, val_cut)
    if val_cut <= train_cut:
        val_cut = min(n - 1, train_cut + 1)

    splits = pd.Series(["test"] * n, dtype=str)
    splits.iloc[:train_cut] = "train"
    splits.iloc[train_cut:val_cut] = "val"
    df["split"] = splits

    cutoffs = {
        "n": n,
        "train_ratio_target": train_ratio,
        "val_ratio_target": val_ratio,
        "train_end_idx": int(train_cut),
        "val_end_idx": int(val_cut),
        "train_end_ts": str(df.iloc[train_cut - 1]["occurred_at"]) if train_cut > 0 else None,
        "val_end_ts": str(df.iloc[val_cut - 1]["occurred_at"]) if val_cut > 0 else None,
        "counts": df["split"].value_counts().to_dict(),
    }
    return df, cutoffs


def _expand_cut_exclusive(df: pd.DataFrame, cut: int) -> int:
    """Move cut forward while next rows share the same occurred_at as last included row."""
    n = len(df)
    if cut <= 0 or cut >= n:
        return cut
    boundary_ts = df.iloc[cut - 1]["occurred_at"]
    while cut < n and df.iloc[cut]["occurred_at"] == boundary_ts:
        cut += 1
    return cut


def assert_time_split_valid(df: pd.DataFrame) -> None:
    train = df.loc[df["split"] == "train", "occurred_at"]
    val = df.loc[df["split"] == "val", "occurred_at"]
    test = df.loc[df["split"] == "test", "occurred_at"]
    if len(train) and len(val) and train.max() > val.min():
        raise AssertionError("Time leakage: train overlaps val")
    if len(val) and len(test) and val.max() > test.min():
        raise AssertionError("Time leakage: val overlaps test")
    if len(train) and len(test) and train.max() > test.min():
        raise AssertionError("Time leakage: train overlaps test")


def write_split_cutoffs(cutoffs: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cutoffs, indent=2, default=str), encoding="utf-8")
