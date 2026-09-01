"""Canonical CSV parsing and point-in-time split preparation for a batch PoC.

This module deliberately contains no model logic.  It turns external rows
into a bounded, deterministic transaction batch that both PostgreSQL and the
existing Behaviour feature scripts can consume.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb

REQUIRED_COLUMNS = (
    "occurred_at",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount",
    "currency",
    "channel",
)

OPTIONAL_COLUMNS = (
    "transaction_id",
    "amount_received",
    "receiving_currency",
    "remarks",
)

_CURRENCY = re.compile(r"^[A-Z]{3}$")


class BatchValidationError(ValueError):
    """The source file or one of its records violates the batch contract."""


@dataclass(frozen=True, slots=True)
class BatchTransaction:
    source_transaction_id: str
    occurred_at: datetime
    from_bank: str
    from_account: str
    to_bank: str
    to_account: str
    amount: Decimal
    currency: str
    amount_received: Decimal
    receiving_currency: str
    channel: str
    remarks: str
    source_line_number: int

    @property
    def from_account_key(self) -> str:
        return f"{self.from_bank}:{self.from_account}"

    @property
    def to_account_key(self) -> str:
        return f"{self.to_bank}:{self.to_account}"


@dataclass(frozen=True, slots=True)
class RejectedRecord:
    line_number: int
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    transactions: list[BatchTransaction]
    rejected: list[RejectedRecord]
    source_sha256: str


def source_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def stable_source_transaction_id(values: dict[str, str]) -> str:
    material = "\x1f".join(
        values[name].strip()
        for name in (
            "occurred_at",
            "from_bank",
            "from_account",
            "to_bank",
            "to_account",
            "amount",
            "currency",
            "channel",
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _required_text(row: dict[str, str | None], name: str) -> str:
    value = (row.get(name) or "").strip()
    if not value:
        raise BatchValidationError(f"{name} is required")
    return value


def _timestamp(value: str) -> datetime:
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise BatchValidationError(f"occurred_at must be ISO-8601: {value!r}") from None
    if parsed.tzinfo is None:
        raise BatchValidationError("occurred_at must include a timezone (Z or ±HH:MM)")
    return parsed.astimezone(UTC)


def _positive_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise BatchValidationError(f"{name} must be a decimal number") from None
    if not parsed.is_finite() or parsed <= 0:
        raise BatchValidationError(f"{name} must be finite and > 0")
    if parsed.as_tuple().exponent < -2:
        raise BatchValidationError(f"{name} supports at most 2 decimal places")
    return parsed


def _iso_currency(value: str, name: str) -> str:
    code = value.strip().upper()
    if not _CURRENCY.fullmatch(code):
        raise BatchValidationError(f"{name} must be an ISO-4217 three-letter code")
    return code


def parse_transaction(row: dict[str, str | None], line_number: int) -> BatchTransaction:
    normalized = {key: (value or "").strip() for key, value in row.items() if key is not None}
    occurred_at_raw = _required_text(normalized, "occurred_at")
    from_bank = _required_text(normalized, "from_bank")
    from_account = _required_text(normalized, "from_account")
    to_bank = _required_text(normalized, "to_bank")
    to_account = _required_text(normalized, "to_account")
    amount = _positive_decimal(_required_text(normalized, "amount"), "amount")
    currency = _iso_currency(_required_text(normalized, "currency"), "currency")
    channel = _required_text(normalized, "channel")[:64]

    if from_bank == to_bank and from_account == to_account:
        raise BatchValidationError("self-loop transactions are not supported by the operational schema")

    amount_received_raw = normalized.get("amount_received") or str(amount)
    receiving_currency_raw = normalized.get("receiving_currency") or currency
    source_id = normalized.get("transaction_id") or stable_source_transaction_id(normalized)
    if len(source_id) > 128:
        raise BatchValidationError("transaction_id must be at most 128 characters")

    return BatchTransaction(
        source_transaction_id=source_id,
        occurred_at=_timestamp(occurred_at_raw),
        from_bank=from_bank,
        from_account=from_account,
        to_bank=to_bank,
        to_account=to_account,
        amount=amount,
        currency=currency,
        amount_received=_positive_decimal(amount_received_raw, "amount_received"),
        receiving_currency=_iso_currency(receiving_currency_raw, "receiving_currency"),
        channel=channel,
        remarks=(normalized.get("remarks") or "")[:2000],
        source_line_number=line_number,
    )


def parse_batch_csv(path: Path, *, max_records: int = 100_000) -> ParsedBatch:
    if max_records < 1:
        raise ValueError("max_records must be >= 1")
    if not path.is_file():
        raise FileNotFoundError(path)

    transactions: list[BatchTransaction] = []
    rejected: list[RejectedRecord] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing = sorted(set(REQUIRED_COLUMNS) - header)
        unknown = sorted(header - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS))
        if missing:
            raise BatchValidationError(f"missing CSV columns: {', '.join(missing)}")
        if unknown:
            raise BatchValidationError(f"unknown CSV columns: {', '.join(unknown)}")

        for line_number, row in enumerate(reader, start=2):
            if len(transactions) + len(rejected) >= max_records:
                raise BatchValidationError(
                    f"batch exceeds max_records={max_records}; split the input or raise the explicit limit"
                )
            try:
                transaction = parse_transaction(row, line_number)
                if transaction.source_transaction_id in seen_ids:
                    raise BatchValidationError("duplicate transaction_id inside the input batch")
                seen_ids.add(transaction.source_transaction_id)
                transactions.append(transaction)
            except BatchValidationError as exc:
                rejected.append(RejectedRecord(line_number=line_number, reason=str(exc)))

    if not transactions:
        raise BatchValidationError("the batch has no valid transactions")
    return ParsedBatch(
        transactions=transactions,
        rejected=rejected,
        source_sha256=source_checksum(path),
    )


def assign_time_splits(transactions: list[BatchTransaction]) -> dict[str, str]:
    """Return deterministic 60/20/20 splits without splitting equal timestamps."""
    ordered = sorted(transactions, key=lambda tx: (tx.occurred_at, tx.source_transaction_id))
    if len(ordered) < 5:
        raise BatchValidationError("at least 5 valid transactions are required to bootstrap the PoC model")

    train_cut = max(1, int(len(ordered) * 0.60))
    val_cut = max(train_cut + 1, int(len(ordered) * 0.80))
    train_cut = _expand_equal_timestamp(ordered, train_cut)
    val_cut = _expand_equal_timestamp(ordered, val_cut)
    if train_cut >= len(ordered) - 1 or val_cut >= len(ordered):
        raise BatchValidationError("the batch needs at least three distinct event timestamps for time splits")

    result: dict[str, str] = {}
    for index, transaction in enumerate(ordered):
        split = "train" if index < train_cut else "val" if index < val_cut else "test"
        result[transaction.source_transaction_id] = split
    return result


def _expand_equal_timestamp(transactions: list[BatchTransaction], cut: int) -> int:
    if cut <= 0 or cut >= len(transactions):
        return cut
    boundary = transactions[cut - 1].occurred_at
    while cut < len(transactions) and transactions[cut].occurred_at == boundary:
        cut += 1
    return cut


def write_feature_duckdb(
    path: Path,
    transactions: list[BatchTransaction],
    splits: dict[str, str],
) -> None:
    """Create the minimal DuckDB contract consumed by Hường's feature job."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """CREATE TABLE transaction (
                   transaction_id VARCHAR PRIMARY KEY,
                   occurred_at TIMESTAMPTZ NOT NULL,
                   from_account_key VARCHAR NOT NULL,
                   to_account_key VARCHAR NOT NULL,
                   amount DOUBLE NOT NULL,
                   split VARCHAR NOT NULL
               )"""
        )
        connection.executemany(
            "INSERT INTO transaction VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    transaction.source_transaction_id,
                    transaction.occurred_at,
                    transaction.from_account_key,
                    transaction.to_account_key,
                    float(transaction.amount),
                    splits[transaction.source_transaction_id],
                )
                for transaction in transactions
            ],
        )
        connection.execute("CREATE INDEX transaction_time_idx ON transaction(occurred_at)")
        connection.execute("CREATE INDEX transaction_from_idx ON transaction(from_account_key, occurred_at)")
        connection.execute("CREATE INDEX transaction_to_idx ON transaction(to_account_key, occurred_at)")
        connection.execute("CREATE INDEX transaction_split_idx ON transaction(split)")
    finally:
        connection.close()
