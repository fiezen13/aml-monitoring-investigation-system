from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from scripts.extract_features import WINDOW_DAYS, extract_features
from scripts.train_behavior_7d import _require_full_li_small


def _build_transaction_db(path: Path) -> None:
    start = datetime(2022, 9, 1, 12, tzinfo=UTC)
    rows = []
    for day in range(10):
        occurred_at = start + timedelta(days=day)
        split = "train" if day < 6 else "val" if day < 8 else "test"
        rows.append((occurred_at, "A", "B", 100.0 + day, split))

    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """CREATE TABLE transaction (
                   occurred_at TIMESTAMPTZ,
                   from_account_key VARCHAR,
                   to_account_key VARCHAR,
                   amount DOUBLE,
                   split VARCHAR
               )"""
        )
        connection.executemany("INSERT INTO transaction VALUES (?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()


def _account_snapshot(path: Path, account: str, day: int) -> pd.Series:
    frame = pd.read_parquet(path)
    expected = pd.Timestamp(datetime(2022, 9, day, 23, 59, 59, tzinfo=UTC))
    matches = frame[(frame["account_key"] == account) & (frame["as_of_ts"] == expected)]
    assert len(matches) == 1
    return matches.iloc[0]


def test_windows_keep_history_across_split_boundaries(tmp_path: Path) -> None:
    db_path = tmp_path / "aml.duckdb"
    output_dir = tmp_path / "features"
    _build_transaction_db(db_path)

    extract_features("7d", db_path, output_dir)
    # Day 9 is in test, but its 7-day feature still sees days 3..9 from all
    # preceding splits. The former split-by-split implementation returned 1.
    seven_day = _account_snapshot(output_dir / "features_test_7d.parquet", "A", 9)
    assert seven_day["txn_count"] == 7
    assert seven_day["active_days"] == 7


def test_full_li_small_guard_rejects_truncated_database() -> None:
    metadata = {"transactions": 381_078, "calendar_span_days": 10}

    try:
        _require_full_li_small(metadata)
    except RuntimeError as exc:
        assert "381,078" in str(exc)
        assert "run_task1_etl.py" in str(exc)
    else:
        raise AssertionError("Expected a truncated DuckDB to fail")


def test_full_li_small_guard_accepts_canonical_post_filter_database() -> None:
    _require_full_li_small({"transactions": 6_119_572, "calendar_span_days": 17})


def test_behavior_model_contract_has_no_long_window() -> None:
    assert WINDOW_DAYS == {"1d": 1, "7d": 7}
