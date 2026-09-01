from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from src.behavior.batch import (
    BatchValidationError,
    assign_time_splits,
    parse_batch_csv,
    parse_transaction,
    write_feature_duckdb,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "contracts/ingestion/examples/behavior-batch-valid.csv"


def test_canonical_example_parses_without_labels() -> None:
    parsed = parse_batch_csv(EXAMPLE)

    assert len(parsed.transactions) == 10
    assert parsed.rejected == []
    assert len(parsed.source_sha256) == 64
    assert parsed.transactions[0].from_account_key == "BANK01:A001"


def test_time_split_is_ordered_and_deterministic() -> None:
    transactions = parse_batch_csv(EXAMPLE).transactions

    first = assign_time_splits(transactions)
    second = assign_time_splits(list(reversed(transactions)))

    assert first == second
    timestamps = {
        split: [tx.occurred_at for tx in transactions if first[tx.source_transaction_id] == split]
        for split in ("train", "val", "test")
    }
    assert max(timestamps["train"]) < min(timestamps["val"])
    assert max(timestamps["val"]) < min(timestamps["test"])


def test_batch_rejects_naive_timestamp_and_unknown_label_column() -> None:
    row = {
        "occurred_at": "2026-08-01T01:00:00",
        "from_bank": "A",
        "from_account": "1",
        "to_bank": "B",
        "to_account": "2",
        "amount": "10.00",
        "currency": "USD",
        "channel": "wire",
    }
    with pytest.raises(BatchValidationError, match="timezone"):
        parse_transaction(row, 2)

    parsed = parse_batch_csv(EXAMPLE)
    self_loop = replace(
        parsed.transactions[0],
        to_bank=parsed.transactions[0].from_bank,
        to_account=parsed.transactions[0].from_account,
    )
    with pytest.raises(BatchValidationError, match="distinct event timestamps"):
        assign_time_splits([self_loop] * 5)


def test_duckdb_bridge_matches_feature_job_contract(tmp_path: Path) -> None:
    transactions = parse_batch_csv(EXAMPLE).transactions
    splits = assign_time_splits(transactions)
    db_path = tmp_path / "batch.duckdb"

    write_feature_duckdb(db_path, transactions, splits)

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM transaction").fetchone()[0] == 10
        assert {row[0] for row in connection.execute("SELECT DISTINCT split FROM transaction").fetchall()} == {
            "train",
            "val",
            "test",
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info('transaction')").fetchall()}
        assert {"occurred_at", "from_account_key", "to_account_key", "amount", "split"} <= columns
    finally:
        connection.close()
