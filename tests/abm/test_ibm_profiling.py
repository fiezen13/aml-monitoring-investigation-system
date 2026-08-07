"""Tests for the IBM AML profiling phases.

The fixture at `tests/fixtures/aml/HI-Sample_Trans.csv` is 203 rows and contains
two deliberately malformed records used by the Kafka producer's DLQ tests. That
makes it the right fixture here too: a profiler that cannot survive a bad row
cannot profile a real file that has one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pytest

from abm.profiling.ibm_behavior import (
    FORBIDDEN_COLUMNS,
    build_account_behavior_profiles,
)
from abm.profiling.ibm_reader import (
    COLUMN_NAMES,
    HeaderMismatchError,
    convert_column,
    iter_batches,
    validate_header,
)
from abm.profiling.ibm_source import profile_ibm_source, write_profile
from abm.profiling.streaming import NumericAccumulator, shannon_entropy

FIXTURE = Path("tests/fixtures/aml/HI-Sample_Trans.csv")


def test_header_with_duplicate_account_columns_is_accepted() -> None:
    validate_header(
        [
            "Timestamp",
            "From Bank",
            "Account",
            "To Bank",
            "Account",
            "Amount Received",
            "Receiving Currency",
            "Amount Paid",
            "Payment Currency",
            "Payment Format",
            "Is Laundering",
        ]
    )


def test_header_mismatch_is_fatal() -> None:
    with pytest.raises(HeaderMismatchError):
        validate_header(["Timestamp", "From Bank", "Account"])


def test_columns_are_read_by_position_not_name() -> None:
    """The two `Account` columns must land in different fields.

    This is the whole reason the reader exists. A name-based reader collapses
    them and every counterparty edge in the dataset becomes a self-loop.
    """
    batch = next(iter_batches(FIXTURE))
    columns = {name: batch.column(index) for index, name in enumerate(COLUMN_NAMES)}
    assert columns["from_account"][1].as_py() == "EDEC9BCC1"
    assert columns["to_account"][1].as_py() == "FE0DC1D12"


def test_bank_identifiers_keep_leading_zeros() -> None:
    """`015768` must not become 15768; they are different banks."""
    batch = next(iter_batches(FIXTURE))
    banks = batch.column(COLUMN_NAMES.index("from_bank")).to_pylist()
    assert "08812" in banks
    assert all(isinstance(bank, str) for bank in banks)


def test_malformed_values_are_counted_not_fatal() -> None:
    """The fixture holds a row with `is_laundering` = 'yes' and a 9-column row."""
    profile = profile_ibm_source(FIXTURE)
    assert profile["parse_failures"]["invalid_row_count"] == 1
    assert profile["columns"][10]["type_conversion_failures"] == 1
    assert profile["row_count"] > 0


def test_conversion_failure_becomes_null_rather_than_raising() -> None:
    column = pa.array(["1", "0", "yes", "1"])
    converted = convert_column(column, "is_laundering")
    assert converted.to_pylist() == [1, 0, None, 1]


def test_profile_records_source_identity(tmp_path: Path) -> None:
    profile = profile_ibm_source(FIXTURE)
    assert profile["source"]["sha256"]
    assert profile["source"]["size_bytes"] == FIXTURE.stat().st_size
    output = write_profile(profile, tmp_path / "profile.json")
    assert json.loads(output.read_text())["row_count"] == profile["row_count"]


def test_truncated_run_is_flagged() -> None:
    """A profile of part of a file must never look like a profile of all of it."""
    profile = profile_ibm_source(FIXTURE, max_rows=10)
    assert profile["truncated_run"] is True
    assert profile["row_count"] == 10


def test_profiling_is_deterministic() -> None:
    """Same bytes, same numbers — quantiles come from a histogram, not sampling."""
    first = profile_ibm_source(FIXTURE)
    second = profile_ibm_source(FIXTURE)
    for key in ("row_count", "amounts", "identifiers", "structure", "categorical"):
        assert first[key] == second[key]


def test_behavior_profile_never_reads_the_label(tmp_path: Path) -> None:
    """Phase 2's central rule, asserted rather than documented.

    If the laundering label enters the behavior frame, archetypes derived from
    it encode the answer and every model trained downstream measures its own
    leakage.
    """
    output = tmp_path / "behavior.csv"
    result = build_account_behavior_profiles(FIXTURE, output=output, report=tmp_path / "summary.json")
    assert result["status"] == "PASS"

    table = pacsv.read_csv(str(output))
    for forbidden in FORBIDDEN_COLUMNS:
        assert forbidden not in table.column_names
    assert not any("launder" in name.lower() for name in table.column_names)

    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["label_usage"]["is_laundering_read"] is False


def test_behavior_profile_excludes_self_transfers_from_counterparties(tmp_path: Path) -> None:
    """An account paying itself is not a counterparty edge.

    Account `0:B4A963116` has exactly two rows in the fixture: it pays itself
    once, and receives once from `010:277CE0BA8`. The self-payment must count as
    a self-transfer and must not appear on either counterparty side; the genuine
    receipt must survive. Both halves matter — dropping self-transfers from the
    counterparty count is only correct if real edges are still kept.
    """
    output = tmp_path / "behavior.csv"
    build_account_behavior_profiles(FIXTURE, output=output, report=tmp_path / "summary.json")
    table = pacsv.read_csv(str(output)).to_pylist()
    rows = {row["account_key"]: row for row in table}

    self_paying = rows["0:B4A963116"]
    assert self_paying["self_transfer_count"] == 1
    assert self_paying["unique_inbound_counterparties"] == 1
    assert self_paying["unique_outbound_counterparties"] == 0


def test_behavior_profile_normalizes_bank_padding(tmp_path: Path) -> None:
    """`070` and `0070` are the same bank, so they must produce one account key."""
    output = tmp_path / "behavior.csv"
    build_account_behavior_profiles(FIXTURE, output=output, report=tmp_path / "summary.json")
    keys = pacsv.read_csv(str(output)).column("account_key").to_pylist()
    assert all(not key.split(":")[0].startswith("0") or key.split(":")[0] == "0" for key in keys)


def test_histogram_quantiles_land_in_the_right_decade() -> None:
    accumulator = NumericAccumulator()
    for value in list(range(1, 1001)):
        accumulator.add(float(value))
    median = accumulator.quantile(0.5)
    assert 450 < median < 550
    assert accumulator.count == 1000
    assert accumulator.maximum == 1000.0


def test_entropy_is_zero_when_one_value_dominates() -> None:
    assert shannon_entropy({"a": 10}) == 0.0
    assert shannon_entropy({"a": 5, "b": 5}) == pytest.approx(1.0)
