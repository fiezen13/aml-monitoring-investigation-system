"""Streaming reader for the IBM AML transaction CSV.

Two properties of the source file dictate everything here.

**Two columns are both named `Account`.**

    Timestamp,From Bank,Account,To Bank,Account,Amount Received,...
                         ^^^^^^^          ^^^^^^^

Any reader that keys on names either renames one column silently or drops it.
`src/aml/csvsource.py` solved this for the Kafka producer by reading positions
instead of names; this module does the same thing for profiling, by handing
PyArrow an explicit ordered name list and skipping the file's own header row.
The position is the contract. The header is only checked to confirm the file is
the one we think it is.

**Identifiers are strings, never numbers.** Bank `015768` without its leading
zero is a different bank, and account `8149656B0` is not a number at all. Every
identifier column is forced to string at parse time.

Amounts are parsed as float64 rather than Decimal. That is safe for *profiling*,
where the outputs are distribution summaries, but it is not safe for generating
a release; the exporter keeps Decimal for that reason.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

# Positional column contract. Names are ours, not the file's, because the file's
# names are not unique.
COLUMN_NAMES: tuple[str, ...] = (
    "timestamp",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "receiving_currency",
    "amount_paid",
    "payment_currency",
    "payment_format",
    "is_laundering",
)

# What the file's own header must say, in this order.
EXPECTED_HEADER: tuple[str, ...] = (
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
)

TIMESTAMP_FORMAT = "%Y/%m/%d %H:%M"

# Every column is read as string and converted afterwards. A profiler's job
# includes reporting how many values do *not* hold the type they are supposed
# to; letting the CSV parser raise on the first bad value would make that
# unmeasurable, and would let one malformed row abort a 32-million-row run.
COLUMN_TYPES: dict[str, pa.DataType] = dict.fromkeys(COLUMN_NAMES, pa.string())

# The type each column is expected to hold once converted.
TARGET_TYPES: dict[str, pa.DataType] = {
    "timestamp": pa.timestamp("s"),
    "from_bank": pa.string(),
    "from_account": pa.string(),
    "to_bank": pa.string(),
    "to_account": pa.string(),
    "amount_received": pa.float64(),
    "receiving_currency": pa.string(),
    "amount_paid": pa.float64(),
    "payment_currency": pa.string(),
    "payment_format": pa.string(),
    "is_laundering": pa.int8(),
}

# 256 MiB of input per block. Large enough that per-batch Python overhead is
# negligible across 32 million rows, small enough that peak memory stays flat.
DEFAULT_BLOCK_SIZE = 256 << 20


class HeaderMismatchError(RuntimeError):
    """The file is not an IBM AML transaction CSV."""


def read_header(path: Path, *, encoding: str = "utf-8") -> list[str]:
    with path.open("r", encoding=encoding, newline="") as handle:
        first = handle.readline()
    return [column.strip() for column in first.rstrip("\r\n").split(",")]


def validate_header(header: list[str]) -> None:
    """Confirm the file matches the positional contract before reading it.

    Compared case-insensitively and whitespace-stripped: Kaggle re-exports vary
    on both. A mismatch stops the run rather than degrading, because reading the
    wrong file by position produces confident nonsense instead of an error.
    """
    if [name.lower() for name in header] != [name.lower() for name in EXPECTED_HEADER]:
        raise HeaderMismatchError(
            "CSV header does not match the IBM AML transaction schema.\n"
            f"  expected: {', '.join(EXPECTED_HEADER)}\n"
            f"  found:    {', '.join(header)}"
        )


class InvalidRowLog:
    """Counts rows the parser could not read, keeping a bounded sample.

    A row with the wrong number of fields is skipped rather than fatal. Aborting
    a 32-million-row profile because one row is malformed would mean never
    profiling a file that has one — but silently dropping rows would understate
    every count in the profile. So they are counted, sampled, and reported.
    """

    SAMPLE_LIMIT = 20

    def __init__(self) -> None:
        self.count = 0
        self.samples: list[dict[str, Any]] = []

    def handler(self, row: Any) -> str:
        self.count += 1
        if len(self.samples) < self.SAMPLE_LIMIT:
            self.samples.append(
                {
                    "source_row_number": row.number,
                    "expected_columns": row.expected_columns,
                    "actual_columns": row.actual_columns,
                    "text": row.text[:400],
                }
            )
        return "skip"

    def summary(self) -> dict[str, Any]:
        return {
            "invalid_row_count": self.count,
            "samples": self.samples,
            "handling": "skipped and counted; excluded from every statistic in this profile",
        }


def iter_batches(
    path: Path,
    *,
    block_size: int = DEFAULT_BLOCK_SIZE,
    max_rows: int | None = None,
    invalid_rows: InvalidRowLog | None = None,
) -> Iterator[pa.RecordBatch]:
    """Yield record batches with the positional column names applied.

    `max_rows` truncates the stream. It exists so a developer can rehearse a
    profiling run on a few million rows before committing to the full file; a
    truncated run must never be published as a profile of the whole file, and
    the profile writer records the truncation for exactly that reason.
    """
    validate_header(read_header(path))
    log = invalid_rows if invalid_rows is not None else InvalidRowLog()
    reader = pacsv.open_csv(
        str(path),
        read_options=pacsv.ReadOptions(
            column_names=list(COLUMN_NAMES),
            skip_rows=1,
            block_size=block_size,
        ),
        parse_options=pacsv.ParseOptions(invalid_row_handler=log.handler),
        convert_options=pacsv.ConvertOptions(column_types=COLUMN_TYPES),
    )
    emitted = 0
    try:
        for batch in reader:
            if max_rows is not None and emitted + batch.num_rows > max_rows:
                batch = batch.slice(0, max_rows - emitted)
            if batch.num_rows == 0:
                break
            emitted += batch.num_rows
            yield batch
            if max_rows is not None and emitted >= max_rows:
                break
    finally:
        reader.close()


# PyArrow's cast has no "null on failure" mode for strings, so unparseable
# values are masked out first. These patterns decide what is castable.
_NUMERIC_PATTERN = r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$"
_INTEGER_PATTERN = r"^[+-]?\d+$"


def convert_column(column: pa.Array, name: str) -> pa.Array:
    """Cast one string column to its target type, nulling values that fail.

    A failed conversion becomes a null, so the caller can count it by comparing
    null counts before and after. Timestamps go through `strptime` because the
    source format (`2022/09/01 00:17`) is not one PyArrow infers.

    The direct cast is tried first because it is the fast path and the IBM files
    are overwhelmingly well-formed; the regex mask only runs for a batch that
    actually contains a bad value, so one malformed row costs one batch of extra
    work rather than slowing down the whole file.
    """
    target = TARGET_TYPES[name]
    if target == pa.string():
        return column
    if pa.types.is_timestamp(target):
        return pc.strptime(column, format=TIMESTAMP_FORMAT, unit="s", error_is_null=True)
    try:
        return pc.cast(column, target)
    except pa.ArrowInvalid:
        pattern = _INTEGER_PATTERN if pa.types.is_integer(target) else _NUMERIC_PATTERN
        castable = pc.match_substring_regex(column, pattern)
        masked = pc.if_else(castable, column, pa.scalar(None, pa.string()))
        return pc.cast(masked, target)


def file_checksum(path: Path, *, chunk_size: int = 8 << 20) -> str:
    """SHA-256 of the raw bytes, streamed.

    The raw file is immutable source evidence. Recording its digest is what lets
    a later release prove which bytes it was derived from.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    """Filename, size, and checksum — the minimum provenance for a source file."""
    return {
        "filename": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": file_checksum(path),
    }
