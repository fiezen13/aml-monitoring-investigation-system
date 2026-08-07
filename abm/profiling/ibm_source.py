"""Phase 1 — profile the raw IBM AML transaction file without modifying it.

The output is a machine-readable description of what is actually in the file:
row count, column types, null and parse failures, value distributions, temporal
extent, and identifier cardinality. It is written once per source file and is
the evidence every later phase cites.

Nothing here writes to the source file, and nothing infers meaning beyond what
the bytes support. Where a number is approximate — quantiles, capped distinct
counts — the field name or an adjacent flag says so.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from abm.profiling.ibm_reader import (
    COLUMN_NAMES,
    EXPECTED_HEADER,
    TARGET_TYPES,
    TIMESTAMP_FORMAT,
    InvalidRowLog,
    convert_column,
    file_identity,
    iter_batches,
    read_header,
)
from abm.profiling.streaming import BINS_PER_DECADE, CappedCounter, CappedSet, NumericAccumulator

PROFILE_SCHEMA_VERSION = "1.0"

# An IBM file has a few thousand banks and a few million accounts. The caps sit
# above both so a normal run is exact, while a pathological file fails loudly
# through the truncation flag instead of exhausting memory.
BANK_CARDINALITY_CAP = 2_000_000
ACCOUNT_CARDINALITY_CAP = 20_000_000

_CATEGORICAL_COLUMNS = ("receiving_currency", "payment_currency", "payment_format")


def _histogram_bins(column: pa.Array) -> dict[int, int]:
    """Bin positive amounts by log10 so quantiles need no per-row storage."""
    positive = pc.filter(column, pc.greater(column, 0))
    if len(positive) == 0:
        return {}
    bins = pc.floor(pc.multiply(pc.log10(positive), float(BINS_PER_DECADE)))
    counts = pc.value_counts(pc.cast(bins, pa.int32()))
    return {row["values"]: row["counts"] for row in counts.to_pylist()}


def _merge_counts(target: dict[Any, int], source: dict[Any, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def account_key(bank: pa.Array, account: pa.Array) -> pa.Array:
    """Join bank and account into one identifier.

    IBM account numbers are unique only within a bank, so `bank:account` is the
    real account identity. Using the bare account number would silently merge
    unrelated accounts that happen to share a number across banks — and the
    profile measures exactly how often that would have happened.
    """
    return pc.binary_join_element_wise(bank, account, ":")


def profile_ibm_source(
    path: Path,
    *,
    max_rows: int | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Stream the whole file once and return its profile."""
    started = datetime.now(UTC)

    rows = 0
    null_counts = dict.fromkeys(COLUMN_NAMES, 0)
    amount_received = NumericAccumulator()
    amount_paid = NumericAccumulator()
    categorical = {name: CappedCounter(cap=10_000) for name in _CATEGORICAL_COLUMNS}
    banks = CappedCounter(cap=BANK_CARDINALITY_CAP)
    label_counts: dict[Any, int] = {}
    currency_pairs: dict[str, int] = {}
    format_by_label: dict[str, dict[int, int]] = {}

    account_keys = CappedSet(cap=ACCOUNT_CARDINALITY_CAP)
    bare_account_numbers = CappedSet(cap=ACCOUNT_CARDINALITY_CAP)

    timestamp_min: int | None = None
    timestamp_max: int | None = None

    self_transfers = 0
    cross_currency = 0
    amount_mismatch = 0

    conversion_failures = dict.fromkeys(COLUMN_NAMES, 0)
    invalid_rows = InvalidRowLog()
    for batch in iter_batches(path, max_rows=max_rows, invalid_rows=invalid_rows):
        rows += batch.num_rows
        raw = {name: batch.column(index) for index, name in enumerate(COLUMN_NAMES)}

        # Convert after reading, so a value that does not hold its declared type
        # is counted rather than fatal. Nulls that appear only after conversion
        # are conversion failures; nulls present beforehand are missing data.
        columns = {}
        for name, column in raw.items():
            null_counts[name] += column.null_count
            converted = convert_column(column, name)
            conversion_failures[name] += converted.null_count - column.null_count
            columns[name] = converted

        for accumulator, name in ((amount_received, "amount_received"), (amount_paid, "amount_paid")):
            column = columns[name]
            accumulator.count += len(column) - column.null_count
            total = pc.sum(column).as_py()
            if total is not None:
                accumulator.total += total
            minimum = pc.min(column).as_py()
            maximum = pc.max(column).as_py()
            if minimum is not None and (accumulator.minimum is None or minimum < accumulator.minimum):
                accumulator.minimum = minimum
            if maximum is not None and (accumulator.maximum is None or maximum > accumulator.maximum):
                accumulator.maximum = maximum
            accumulator.zero_count += pc.sum(pc.cast(pc.equal(column, 0), pa.int64())).as_py() or 0
            accumulator.negative_count += pc.sum(pc.cast(pc.less(column, 0), pa.int64())).as_py() or 0
            _merge_counts(accumulator.histogram, _histogram_bins(column))

        for name in _CATEGORICAL_COLUMNS:
            for row in pc.value_counts(columns[name]).to_pylist():
                value = row["values"]
                if value is None:
                    continue
                counter = categorical[name]
                counter.counts[value] = counter.counts.get(value, 0) + row["counts"]

        for name in ("from_bank", "to_bank"):
            for row in pc.value_counts(columns[name]).to_pylist():
                if row["values"] is not None:
                    banks.counts[row["values"]] = banks.counts.get(row["values"], 0) + row["counts"]

        _merge_counts(
            label_counts, {r["values"]: r["counts"] for r in pc.value_counts(columns["is_laundering"]).to_pylist()}
        )

        from_key = account_key(columns["from_bank"], columns["from_account"])
        to_key = account_key(columns["to_bank"], columns["to_account"])
        for keys in (from_key, to_key):
            for value in pc.unique(keys).to_pylist():
                if value is not None:
                    account_keys.add(value)
        for name in ("from_account", "to_account"):
            for value in pc.unique(columns[name]).to_pylist():
                if value is not None:
                    bare_account_numbers.add(value)

        batch_min = pc.min(columns["timestamp"]).as_py()
        batch_max = pc.max(columns["timestamp"]).as_py()
        if batch_min is not None:
            epoch_min = int(batch_min.replace(tzinfo=UTC).timestamp())
            timestamp_min = epoch_min if timestamp_min is None else min(timestamp_min, epoch_min)
        if batch_max is not None:
            epoch_max = int(batch_max.replace(tzinfo=UTC).timestamp())
            timestamp_max = epoch_max if timestamp_max is None else max(timestamp_max, epoch_max)

        self_transfers += pc.sum(pc.cast(pc.equal(from_key, to_key), pa.int64())).as_py() or 0
        cross = pc.not_equal(columns["receiving_currency"], columns["payment_currency"])
        cross_currency += pc.sum(pc.cast(cross, pa.int64())).as_py() or 0
        amount_mismatch += (
            pc.sum(pc.cast(pc.not_equal(columns["amount_received"], columns["amount_paid"]), pa.int64())).as_py() or 0
        )

        pair_keys = pc.binary_join_element_wise(columns["payment_currency"], columns["receiving_currency"], " -> ")
        for row in pc.value_counts(pair_keys).to_pylist():
            if row["values"] is not None:
                currency_pairs[row["values"]] = currency_pairs.get(row["values"], 0) + row["counts"]

        for label in (0, 1):
            mask = pc.equal(columns["is_laundering"], label)
            selected = pc.filter(columns["payment_format"], mask)
            bucket = format_by_label.setdefault(str(label), {})
            for row in pc.value_counts(selected).to_pylist():
                if row["values"] is not None:
                    bucket[row["values"]] = bucket.get(row["values"], 0) + row["counts"]

        if progress is not None:
            progress(rows)

    finished = datetime.now(UTC)
    labelled = label_counts.get(1, 0)

    return {
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "profiled_at": started.isoformat(timespec="seconds"),
        "profiling_duration_seconds": round((finished - started).total_seconds(), 1),
        "source": file_identity(path),
        "truncated_run": max_rows is not None,
        "max_rows_requested": max_rows,
        "row_count": rows,
        "header": {
            "declared_in_file": read_header(path),
            "expected": list(EXPECTED_HEADER),
            "duplicate_column_names": ["Account"],
            "read_strategy": "positional; PyArrow receives explicit unique names and skips the file header",
        },
        "columns": _column_report(rows, null_counts, conversion_failures),
        "parse_failures": invalid_rows.summary(),
        "amounts": {
            "amount_received": amount_received.summary(),
            "amount_paid": amount_paid.summary(),
            "rows_where_paid_differs_from_received": amount_mismatch,
            "note": (
                "Amounts are parsed as float64 for profiling. Release generation "
                "must use Decimal; float64 here only summarizes distributions."
            ),
        },
        "temporal": _temporal_report(timestamp_min, timestamp_max, conversion_failures["timestamp"]),
        "categorical": {name: counter.summary(top=40) for name, counter in categorical.items()},
        "currency_pairs": {
            "distinct": len(currency_pairs),
            "cross_currency_rows": cross_currency,
            "cross_currency_share": cross_currency / rows if rows else None,
            "top_values": _top(currency_pairs, 25),
        },
        "identifiers": {
            "distinct_banks": len(banks.counts),
            "banks_truncated": banks.truncated,
            "distinct_account_keys_bank_qualified": len(account_keys),
            "distinct_bare_account_numbers": len(bare_account_numbers),
            "account_numbers_reused_across_banks": len(account_keys) - len(bare_account_numbers),
            "account_key_definition": "bank + ':' + account_number",
            "top_banks_by_transaction_leg": _top(banks.counts, 20),
            "truncated": account_keys.truncated or bare_account_numbers.truncated,
        },
        "structure": {
            "self_transfer_rows": self_transfers,
            "self_transfer_share": self_transfers / rows if rows else None,
            "self_transfer_note": (
                "Rows whose source and destination account keys are identical. "
                "These are internal movements, not counterparty edges, and must be "
                "excluded from graph degree statistics."
            ),
        },
        "label": {
            "column": "is_laundering",
            "counts": {str(key): value for key, value in sorted(label_counts.items(), key=lambda i: str(i[0]))},
            "positive_rows": labelled,
            "positive_share": labelled / rows if rows else None,
            "payment_format_by_label": {key: _top(value, 15) for key, value in sorted(format_by_label.items())},
            "usage_rule": (
                "Excluded from behavioral profiling, archetype derivation, and KYC "
                "matching. Retained only for the separate ground_truth release subtree."
            ),
        },
    }


def _column_report(rows: int, null_counts: dict[str, int], conversion_failures: dict[str, int]) -> list[dict[str, Any]]:
    positions = {name: index for index, name in enumerate(COLUMN_NAMES)}
    return [
        {
            "position": positions[name],
            "profile_name": name,
            "source_header": EXPECTED_HEADER[positions[name]],
            "read_as": "string",
            "target_type": str(TARGET_TYPES[name]),
            "null_count": null_counts[name],
            "null_rate": null_counts[name] / rows if rows else None,
            "type_conversion_failures": conversion_failures[name],
        }
        for name in COLUMN_NAMES
    ]


def _temporal_report(minimum: int | None, maximum: int | None, failures: int) -> dict[str, Any]:
    if minimum is None or maximum is None:
        return {"parse_failures": failures, "first_timestamp": None, "last_timestamp": None}
    first = datetime.fromtimestamp(minimum, UTC)
    last = datetime.fromtimestamp(maximum, UTC)
    return {
        "format": TIMESTAMP_FORMAT,
        "resolution": "minute",
        "timezone": "none declared in source; treated as naive local time",
        "parse_failures": failures,
        "first_timestamp": first.isoformat().replace("+00:00", "Z"),
        "last_timestamp": last.isoformat().replace("+00:00", "Z"),
        "span_days": round((maximum - minimum) / 86400, 2),
    }


def _top(counts: dict[str, int], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
    return [{"value": key, "count": value} for key, value in ordered[:limit]]


def write_profile(profile: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
