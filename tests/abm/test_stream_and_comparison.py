"""Tests for the streaming writer and the IBM comparison.

The streaming rewrite exists so the full release fits in memory. These check the
properties that rewrite could plausibly have broken: identifier continuity across
the hard-negative boundary, the geometric-mean scale, and the vectorised key
lookup that replaced per-row dict access.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from abm.canonical.ibm_comparison import RELATIVE_TOLERANCE, _compare
from abm.canonical.stream import (
    AccountColumns,
    _geometric_mean,
    append_hard_negative_transactions,
    redraw_times_chunked,
    stream_transactions,
)
from abm.canonical.transactions import ASSUME_DIURNAL_PROFILE

SECONDS_PER_DAY = 86_400
BASE_DAY = 19_236  # 2022-09-01


def _accounts(count: int) -> list[dict]:
    return [
        {
            "_key": f"bank{index % 7}:ACCT{index:05d}",
            "account_id": f"ACC-{index + 1:08d}",
            "_scale": 2.0 + index,
            "_entity": {
                "digital_usage_segment": ("HIGH", "MEDIUM", "LOW", "NONE")[index % 4],
                "income_band": "Q5" if index % 5 == 0 else "Q2",
            },
        }
        for index in range(count)
    ]


def _raw(accounts: list[dict], rows: int) -> pa.Table:
    keys = [account["_key"] for account in accounts]
    rng = np.random.default_rng(4)
    return pa.table(
        {
            "from_key": pa.array([keys[int(rng.integers(0, len(keys)))] for _ in range(rows)]),
            "to_key": pa.array([keys[int(rng.integers(0, len(keys)))] for _ in range(rows)]),
            "timestamp_epoch": pa.array(
                [BASE_DAY * SECONDS_PER_DAY + int(rng.integers(0, 4 * SECONDS_PER_DAY)) for _ in range(rows)],
                pa.int64(),
            ),
            "amount": pa.array(rng.uniform(1.0, 500.0, size=rows)),
            "is_laundering": pa.array([1 if index % 37 == 0 else 0 for index in range(rows)], pa.int8()),
        }
    )


def _partition(day: int, first: int, last: int) -> str:
    return "EARLY"


TX_COLUMNS = [
    "transaction_id",
    "event_id",
    "schema_version",
    "timestamp",
    "source_account_id",
    "destination_account_id",
    "source_counterparty_token",
    "destination_counterparty_token",
    "amount",
    "currency",
    "payment_format",
    "channel",
    "transaction_type",
    "merchant_id",
    "time_partition",
]
LABEL_COLUMNS = ["transaction_id", "is_laundering", "scenario_id", "scenario_stage", "source"]


def _run(tmp_path: Path, accounts: list[dict], raw: pa.Table, pattern_lookup=None) -> dict:
    columns = AccountColumns(accounts)
    return stream_transactions(
        raw=raw,
        columns=columns,
        pattern_lookup=pattern_lookup or {},
        transactions_path=tmp_path / "transactions.csv",
        labels_path=tmp_path / "labels.csv",
        transaction_columns=TX_COLUMNS,
        label_columns=LABEL_COLUMNS,
        merchant_ids=["MER-00000001", "MER-00000002"],
        diurnal_profile=ASSUME_DIURNAL_PROFILE,
        international_wire_share=0.09,
        rng=np.random.default_rng(11),
        time_partition=_partition,
    )


# ---------------------------------------------------------------- scale maths


def test_geometric_mean_matches_the_scalar_definition() -> None:
    first = np.array([4.0, 9.0, np.nan, np.nan])
    second = np.array([9.0, np.nan, 5.0, np.nan])
    result = _geometric_mean(first, second)
    assert result[0] == pytest.approx(6.0)
    assert result[1] == pytest.approx(9.0)
    assert result[2] == pytest.approx(5.0)
    assert np.isnan(result[3])


# ------------------------------------------------------------- account lookup


def test_account_positions_are_vectorised_and_mark_external_as_minus_one() -> None:
    accounts = _accounts(5)
    columns = AccountColumns(accounts)
    keys = pa.array([accounts[2]["_key"], "not:present", accounts[0]["_key"]])
    positions = columns.positions(keys)
    assert positions[1] == -1
    assert columns.account_ids[positions[0]] == accounts[2]["account_id"]
    assert columns.account_ids[positions[2]] == accounts[0]["account_id"]


# ------------------------------------------------------------------ streaming


def test_stream_writes_every_row_with_unique_ids(tmp_path: Path) -> None:
    accounts = _accounts(40)
    stats = _run(tmp_path, accounts, _raw(accounts, 5_000))

    rows = list(csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8")))
    labels = list(csv.DictReader((tmp_path / "labels.csv").open(encoding="utf-8")))

    assert len(rows) == stats["written"] == len(labels)
    ids = [row["transaction_id"] for row in rows]
    assert len(set(ids)) == len(ids)
    assert len({row["event_id"] for row in rows}) == len(rows)


def test_stream_and_labels_stay_aligned(tmp_path: Path) -> None:
    accounts = _accounts(30)
    _run(tmp_path, accounts, _raw(accounts, 3_000))
    rows = list(csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8")))
    labels = list(csv.DictReader((tmp_path / "labels.csv").open(encoding="utf-8")))
    assert [row["transaction_id"] for row in rows] == [row["transaction_id"] for row in labels]


def test_amounts_are_positive_integers(tmp_path: Path) -> None:
    accounts = _accounts(25)
    _run(tmp_path, accounts, _raw(accounts, 2_000))
    for row in csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8")):
        amount = row["amount"]
        assert amount.isdigit()
        assert int(amount) >= 1


def test_timestamps_come_out_in_ascending_order(tmp_path: Path) -> None:
    """Rows are written in the source's time order, so the file is sorted."""
    accounts = _accounts(20)
    _run(tmp_path, accounts, _raw(accounts, 2_000))
    stamps = [row["timestamp"] for row in csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8"))]
    assert stamps == sorted(stamps)


def test_chunk_boundary_does_not_break_numbering(tmp_path: Path, monkeypatch) -> None:
    """Ids must run continuously across chunks, not restart inside each one."""
    monkeypatch.setattr("abm.canonical.stream.CHUNK_ROWS", 250)
    accounts = _accounts(20)
    _run(tmp_path, accounts, _raw(accounts, 1_200))
    ids = [
        int(row["transaction_id"].split("-")[1])
        for row in csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8"))
    ]
    assert ids == list(range(1, len(ids) + 1))


def test_hard_negatives_continue_the_id_sequence(tmp_path: Path) -> None:
    """The collision this guards against produced 645 duplicate ids once."""
    accounts = _accounts(30)
    stats = _run(tmp_path, accounts, _raw(accounts, 2_000))

    class Episode:
        account_id = accounts[0]["account_id"]
        legs = [{"inbound": True, "amount_vnd": 5_000_000.0, "day": BASE_DAY} for _ in range(9)]

    added = append_hard_negative_transactions(
        episodes=[Episode()],
        account_lookup={account["account_id"]: account for account in accounts},
        transactions_path=tmp_path / "transactions.csv",
        labels_path=tmp_path / "labels.csv",
        offset=stats["written"],
        first_day=BASE_DAY,
        last_day=BASE_DAY + 3,
        rng=np.random.default_rng(2),
        time_partition=_partition,
    )
    assert added == 9

    ids = [row["transaction_id"] for row in csv.DictReader((tmp_path / "transactions.csv").open(encoding="utf-8"))]
    assert len(set(ids)) == len(ids) == stats["written"] + 9


def test_flagged_accounts_are_collected_during_the_pass(tmp_path: Path) -> None:
    accounts = _accounts(30)
    stats = _run(tmp_path, accounts, _raw(accounts, 3_000))
    assert stats["flagged_accounts"]
    assert all(value.startswith("ACC-") for value in stats["flagged_accounts"])


def test_pattern_lookup_tags_matching_rows(tmp_path: Path) -> None:
    accounts = _accounts(15)
    raw = _raw(accounts, 500)
    columns = AccountColumns(accounts)
    positions = columns.positions(raw.column("from_key").combine_chunks())
    targets = columns.positions(raw.column("to_key").combine_chunks())
    stamps = raw.column("timestamp_epoch").to_numpy(zero_copy_only=False)

    lookup = {
        (int(positions[0]), int(targets[0]), int(stamps[0])): ("SCN-000001", "LAYERING"),
    }
    stats = _run(tmp_path, accounts, raw, pattern_lookup=lookup)
    assert stats["scenario_matches"] >= 1

    tagged = [row for row in csv.DictReader((tmp_path / "labels.csv").open(encoding="utf-8")) if row["scenario_id"]]
    assert tagged
    assert tagged[0]["source"] == "IBM_PATTERNS"


# ------------------------------------------------------------- time redraw


def test_chunked_redraw_preserves_day_and_order() -> None:
    rng = np.random.default_rng(3)
    stamps = np.array(
        [
            BASE_DAY * SECONDS_PER_DAY + 10,
            BASE_DAY * SECONDS_PER_DAY + 50_000,
            (BASE_DAY + 1) * SECONDS_PER_DAY + 700,
        ],
        dtype=np.int64,
    )
    rebuilt = redraw_times_chunked(stamps, rng, ASSUME_DIURNAL_PROFILE)
    assert list(stamps // SECONDS_PER_DAY) == list(rebuilt // SECONDS_PER_DAY)
    assert list(np.argsort(stamps)) == list(np.argsort(rebuilt))


# ------------------------------------------------------------- comparison


def test_comparison_passes_on_identical_distributions() -> None:
    values = np.arange(1.0, 1001.0)
    result = _compare("x", values, values.copy())
    assert result["verdict"] == "PASS"
    assert result["worst_relative_deviation"] == 0.0


def test_comparison_flags_a_shifted_distribution() -> None:
    """The small release's median account is 9.67x IBM's; this must not pass."""
    result = _compare("x", np.arange(1.0, 1001.0), np.arange(1.0, 1001.0) * 10)
    assert result["verdict"] == "REVIEW"
    assert result["worst_relative_deviation"] > RELATIVE_TOLERANCE
