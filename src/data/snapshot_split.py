"""Shared snapshot time-split helper (Graph + Isolation Forest).

Contract: docs/graph_feature_spec.md §5 / docs/graph_branch_plan.md §2.2.1
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

WINDOW_7D = "7d"
FEATURE_SCHEMA_VERSION = "graph_features_v1"


def parse_utc(ts: str | datetime | pd.Timestamp) -> pd.Timestamp:
    """Parse to timezone-aware UTC Timestamp."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t


def load_split_cutoffs(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def assign_snapshot_split(
    as_of_ts: str | datetime | pd.Timestamp,
    split_cutoffs: Mapping[str, Any],
) -> str:
    """
    Assign sample_split by as_of_ts (not by mix of transaction.split in window).

    if as_of_ts <= train_end_ts -> train
    elif as_of_ts <= val_end_ts -> val
    else -> test
    """
    as_of = parse_utc(as_of_ts)
    train_end = parse_utc(split_cutoffs["train_end_ts"])
    val_end = parse_utc(split_cutoffs["val_end_ts"])
    if as_of <= train_end:
        return "train"
    if as_of <= val_end:
        return "val"
    return "test"


def snapshot_window_bounds(snapshot_date: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Half-open 7d window for calendar date D (UTC):
      end_ts = (D + 1 day) 00:00:00 UTC
      start_ts = end_ts - 7 days
    """
    end_ts = pd.Timestamp(datetime(snapshot_date.year, snapshot_date.month, snapshot_date.day, tzinfo=timezone.utc))
    end_ts = end_ts + pd.Timedelta(days=1)
    start_ts = end_ts - pd.Timedelta(days=7)
    return start_ts, end_ts


def candidate_snapshot_dates(occurred_at: pd.Series) -> list[date]:
    """Default candidate D from date(t_min) through date(t_max) UTC."""
    if occurred_at.empty:
        return []
    ts = pd.to_datetime(occurred_at, utc=True)
    t_min = ts.min()
    t_max = ts.max()
    d0 = t_min.date()
    d1 = t_max.date()
    out: list[date] = []
    d = d0
    while d <= d1:
        start_ts, end_ts = snapshot_window_bounds(d)
        if start_ts < t_max and end_ts > t_min:
            out.append(d)
        d = d + timedelta(days=1)
    return out
