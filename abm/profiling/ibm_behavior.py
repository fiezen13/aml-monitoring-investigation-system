"""Phase 2 — derive a behavior profile for every IBM account.

The point of this step is to describe what each account *does*, so that later
phases can match a synthetic Vietnamese KYC customer to a real behavioral
pattern instead of inventing one. It answers questions like: does this account
receive from many parties and pay out to few? Does it move money on a monthly
rhythm or a daily one? Is its turnover large relative to its typical payment?

**The laundering label is not read here.** It is not a feature, not a filter,
and not a grouping key. Normal-customer archetypes must be derivable by a bank
that has never seen a label, otherwise the archetypes encode the answer and
every downstream model is measuring itself. `is_laundering` is excluded at the
column level, and a test asserts the column never enters the feature frame.

Account identity is `normalized_bank:account_number`. Bank identifiers in the
transaction file are zero-padded inconsistently — the same bank appears as both
`020` and `0020` — so the padding is stripped before the key is formed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from abm.profiling.ibm_reader import (
    COLUMN_NAMES,
    InvalidRowLog,
    convert_column,
    file_identity,
    iter_batches,
)

BEHAVIOR_SCHEMA_VERSION = "1.0"

# Columns that may never reach the behavior frame.
FORBIDDEN_COLUMNS = ("is_laundering",)

SECONDS_PER_DAY = 86_400

# 1970-01-01 was a Thursday, which is index 3 when Monday is 0.
_EPOCH_WEEKDAY_OFFSET = 3
_WEEKEND_DAYS = (5, 6)

# "Night" is outside 06:00-22:00. The source has no timezone, so this is a
# property of the simulator's clock, not of any real local time.
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6


class CategoryEncoder:
    """Maps a small set of repeated strings to compact integer codes.

    Currency and payment format have 15 and 7 values across 32 million rows.
    Holding them as strings would cost hundreds of megabytes for no benefit;
    holding them as int8 costs 32 MB and decodes exactly.
    """

    def __init__(self) -> None:
        self.values: list[str] = []
        self._index: dict[str, int] = {}

    def encode(self, column: pa.Array) -> pa.Array:
        for value in pc.unique(column).to_pylist():
            if value is not None and value not in self._index:
                self._index[value] = len(self.values)
                self.values.append(value)
        codes = pc.index_in(column, value_set=pa.array(self.values, pa.string()))
        return pc.cast(codes, pa.int16())

    def decode(self, code: int | None) -> str | None:
        if code is None or code < 0 or code >= len(self.values):
            return None
        return self.values[code]


def _load_entity_reference(path: Path) -> dict[str, tuple[str, str]]:
    """Read `HI-*_accounts.csv` into account_key -> (entity_id, entity_kind).

    The accounts file is the only place IBM states which accounts belong to the
    same party and what kind of party that is. `Entity Name` is a label such as
    `Corporation #183669`; the word before the `#` is the legal form, and that
    prefix is the whole of what this function keeps.
    """
    table = pacsv.read_csv(
        str(path),
        convert_options=pacsv.ConvertOptions(
            column_types={
                "Bank ID": pa.string(),
                "Account Number": pa.string(),
                "Entity ID": pa.string(),
                "Entity Name": pa.string(),
            }
        ),
    )
    keys = pc.binary_join_element_wise(
        _normalize_bank(table.column("Bank ID").combine_chunks()),
        table.column("Account Number").combine_chunks(),
        ":",
    )
    kinds = pc.utf8_trim_whitespace(pc.list_element(pc.split_pattern(table.column("Entity Name"), " #"), 0))
    entity_ids = table.column("Entity ID").to_pylist()
    return {
        key: (entity_id, kind)
        for key, entity_id, kind in zip(keys.to_pylist(), entity_ids, kinds.to_pylist(), strict=True)
        if key is not None
    }


def _normalize_bank(column: pa.Array) -> pa.Array:
    """Strip leading zeros so `020` and `0020` are the same bank.

    An all-zero identifier collapses to `0` rather than to the empty string.
    """
    stripped = pc.utf8_ltrim(column, characters="0")
    return pc.if_else(pc.equal(pc.utf8_length(stripped), 0), pa.scalar("0"), stripped)


def account_key(bank: pa.Array, account: pa.Array) -> pa.Array:
    return pc.binary_join_element_wise(_normalize_bank(bank), account, ":")


def _read_transaction_frame(
    path: Path, *, max_rows: int | None, progress: Any
) -> tuple[pa.Table, CategoryEncoder, CategoryEncoder, dict[str, Any]]:
    """Stream the CSV into one compact in-memory frame.

    Roughly 50 bytes per row survive into the frame, so 32 million rows need
    about 1.6 GB. That is the memory ceiling of this phase; `max_rows` exists
    for machines that cannot pay it.
    """
    currency = CategoryEncoder()
    payment_format = CategoryEncoder()
    invalid_rows = InvalidRowLog()
    chunks: list[pa.RecordBatch] = []
    rows = 0

    for batch in iter_batches(path, max_rows=max_rows, invalid_rows=invalid_rows):
        raw = {name: batch.column(index) for index, name in enumerate(COLUMN_NAMES)}
        columns = {name: convert_column(column, name) for name, column in raw.items() if name not in FORBIDDEN_COLUMNS}
        seconds = pc.cast(columns["timestamp"], pa.int64())
        day = pc.cast(pc.divide(seconds, SECONDS_PER_DAY), pa.int32())
        hour = pc.cast(
            pc.divide(pc.subtract(seconds, pc.multiply(pc.cast(day, pa.int64()), SECONDS_PER_DAY)), 3600), pa.int8()
        )
        weekday = pc.cast(
            pc.subtract(
                pc.add(day, _EPOCH_WEEKDAY_OFFSET),
                pc.multiply(pc.divide(pc.add(day, _EPOCH_WEEKDAY_OFFSET), 7), 7),
            ),
            pa.int8(),
        )

        chunks.append(
            pa.RecordBatch.from_arrays(
                [
                    account_key(columns["from_bank"], columns["from_account"]),
                    account_key(columns["to_bank"], columns["to_account"]),
                    columns["amount_paid"],
                    day,
                    pc.cast(
                        pc.or_(pc.greater_equal(hour, NIGHT_START_HOUR), pc.less(hour, NIGHT_END_HOUR)),
                        pa.int8(),
                    ),
                    pc.cast(pc.is_in(weekday, value_set=pa.array(_WEEKEND_DAYS, pa.int8())), pa.int8()),
                    currency.encode(columns["payment_currency"]),
                    payment_format.encode(columns["payment_format"]),
                ],
                names=[
                    "from_key",
                    "to_key",
                    "amount",
                    "day",
                    "is_night",
                    "is_weekend",
                    "currency",
                    "format",
                ],
            )
        )
        rows += batch.num_rows
        if progress is not None:
            progress(rows)

    table = pa.Table.from_batches(chunks)
    del chunks
    meta = {"row_count": rows, "parse_failures": invalid_rows.summary()}
    return table, currency, payment_format, meta


def _directional_stats(table: pa.Table, *, key: str, counterparty: str, prefix: str) -> pa.Table:
    """Aggregate one direction of activity for every account."""
    external = table.filter(pc.not_equal(table.column("from_key"), table.column("to_key")))
    counterparties = (
        external.select([key, counterparty])
        .group_by([key, counterparty])
        .aggregate([])
        .group_by(key)
        .aggregate([(counterparty, "count")])
        .rename_columns([key, f"{prefix}_unique_counterparties"])
    )
    stats = (
        table.select([key, "amount", "day", "is_night", "is_weekend", "currency", "format"])
        .group_by(key)
        .aggregate(
            [
                ("amount", "count"),
                ("amount", "sum"),
                ("amount", "mean"),
                ("amount", "max"),
                ("amount", "approximate_median"),
                ("day", "min"),
                ("day", "max"),
                ("is_night", "sum"),
                ("is_weekend", "sum"),
                ("currency", "count_distinct"),
                ("format", "count_distinct"),
            ]
        )
        .rename_columns(
            [
                key,
                f"{prefix}_count",
                f"{prefix}_total_amount",
                f"{prefix}_mean_amount",
                f"{prefix}_max_amount",
                f"{prefix}_median_amount",
                f"{prefix}_first_day",
                f"{prefix}_last_day",
                f"{prefix}_night_count",
                f"{prefix}_weekend_count",
                f"{prefix}_distinct_currencies",
                f"{prefix}_distinct_formats",
            ]
        )
    )
    return stats.join(counterparties, keys=key, join_type="left outer")


def _dominant_category(table: pa.Table, column: str) -> pa.Table:
    """The most-used value of a low-cardinality column, per account.

    Both directions of activity count: an account's payment-format habit is not
    direction-specific. The intermediate table has one row per account and value,
    a few million rows at most, so sorting it to take the top value per account
    is cheap.
    """
    legs = pa.concat_tables(
        [
            table.select(["from_key", column]).rename_columns(["account_key", column]),
            table.select(["to_key", column]).rename_columns(["account_key", column]),
        ]
    )
    counted = (
        legs.group_by(["account_key", column])
        .aggregate([(column, "count")])
        .rename_columns(["account_key", column, "n"])
    )
    ordered = counted.sort_by([("account_key", "ascending"), ("n", "descending"), (column, "ascending")])
    top = (
        ordered.group_by("account_key", use_threads=False)
        .aggregate([(column, "first"), ("n", "first")])
        .rename_columns(["account_key", f"dominant_{column}", f"dominant_{column}_count"])
    )
    return top


def _active_days(table: pa.Table) -> pa.Table:
    """Distinct calendar days on which an account did anything at all."""
    legs = pa.concat_tables(
        [
            table.select(["from_key", "day"]).rename_columns(["account_key", "day"]),
            table.select(["to_key", "day"]).rename_columns(["account_key", "day"]),
        ]
    )
    return (
        legs.group_by(["account_key", "day"])
        .aggregate([])
        .group_by("account_key")
        .aggregate([("day", "count")])
        .rename_columns(["account_key", "active_days"])
    )


def _self_transfers(table: pa.Table) -> pa.Table:
    internal = table.filter(pc.equal(table.column("from_key"), table.column("to_key")))
    return (
        internal.select(["from_key", "amount"])
        .group_by("from_key")
        .aggregate([("amount", "count"), ("amount", "sum")])
        .rename_columns(["account_key", "self_transfer_count", "self_transfer_amount"])
    )


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def build_account_behavior_profiles(
    path: Path,
    *,
    output: Path,
    report: Path,
    accounts: Path | None = None,
    max_rows: int | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Produce the per-account behavior CSV and a summary report."""
    started = datetime.now(UTC)
    table, currency, payment_format, meta = _read_transaction_frame(path, max_rows=max_rows, progress=progress)

    outgoing = _directional_stats(table, key="from_key", counterparty="to_key", prefix="out")
    incoming = _directional_stats(table, key="to_key", counterparty="from_key", prefix="in")
    outgoing = outgoing.rename_columns(["account_key", *outgoing.column_names[1:]])
    incoming = incoming.rename_columns(["account_key", *incoming.column_names[1:]])

    merged = outgoing.join(incoming, keys="account_key", join_type="full outer")
    merged = merged.join(_active_days(table), keys="account_key", join_type="left outer")
    merged = merged.join(_self_transfers(table), keys="account_key", join_type="left outer")
    merged = merged.join(_dominant_category(table, "currency"), keys="account_key", join_type="left outer")
    merged = merged.join(_dominant_category(table, "format"), keys="account_key", join_type="left outer")

    entities = _load_entity_reference(accounts) if accounts else {}
    observed_days = pc.max(table.column("day")).as_py() - pc.min(table.column("day")).as_py() + 1
    epoch_day = pc.min(table.column("day")).as_py()
    del table

    rows = merged.to_pylist()
    del merged
    rows.sort(key=lambda row: row["account_key"])

    records = [
        _behavior_record(
            row,
            currency=currency,
            payment_format=payment_format,
            entities=entities,
            observed_days=observed_days,
        )
        for row in rows
    ]
    del rows

    _write_csv(records, output)
    summary = _summarize(
        records,
        source=file_identity(path),
        accounts_source=file_identity(accounts) if accounts else None,
        meta=meta,
        observed_days=observed_days,
        epoch_day=epoch_day,
        started=started,
        truncated=max_rows is not None,
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "status": "PASS",
        "accounts_profiled": len(records),
        "transactions_read": meta["row_count"],
        "output": str(output.resolve()),
        "report": str(report.resolve()),
    }


def _behavior_record(
    row: dict[str, Any],
    *,
    currency: CategoryEncoder,
    payment_format: CategoryEncoder,
    entities: dict[str, tuple[str, str]],
    observed_days: int,
) -> dict[str, Any]:
    """Turn one joined aggregate row into the documented behavior schema."""
    out_count = row.get("out_count") or 0
    in_count = row.get("in_count") or 0
    total_count = out_count + in_count
    out_total = row.get("out_total_amount") or 0.0
    in_total = row.get("in_total_amount") or 0.0
    out_unique = row.get("out_unique_counterparties") or 0
    in_unique = row.get("in_unique_counterparties") or 0
    active_days = row.get("active_days") or 0

    first_day = min(value for value in (row.get("out_first_day"), row.get("in_first_day")) if value is not None)
    last_day = max(value for value in (row.get("out_last_day"), row.get("in_last_day")) if value is not None)
    span_days = last_day - first_day + 1

    night = (row.get("out_night_count") or 0) + (row.get("in_night_count") or 0)
    weekend = (row.get("out_weekend_count") or 0) + (row.get("in_weekend_count") or 0)

    entity_id, entity_kind = entities.get(row["account_key"], (None, None))

    record: dict[str, Any] = {
        "account_key": row["account_key"],
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "transaction_count": total_count,
        "incoming_transaction_count": in_count,
        "outgoing_transaction_count": out_count,
        "total_incoming_amount": round(in_total, 2),
        "total_outgoing_amount": round(out_total, 2),
        "mean_incoming_amount": _round(row.get("in_mean_amount")),
        "mean_outgoing_amount": _round(row.get("out_mean_amount")),
        "median_incoming_amount": _round(row.get("in_median_amount")),
        "median_outgoing_amount": _round(row.get("out_median_amount")),
        "max_transaction_amount": _round(
            max(
                (value for value in (row.get("in_max_amount"), row.get("out_max_amount")) if value is not None),
                default=None,
            )
        ),
        "unique_inbound_counterparties": in_unique,
        "unique_outbound_counterparties": out_unique,
        "self_transfer_count": row.get("self_transfer_count") or 0,
        "active_days": active_days,
        "first_active_day_index": first_day,
        "last_active_day_index": last_day,
        "observed_span_days": span_days,
        "activity_density": _round(_safe_ratio(active_days, span_days), 4),
        "transactions_per_active_day": _round(_safe_ratio(total_count, active_days), 4),
        "transactions_per_observed_day": _round(_safe_ratio(total_count, observed_days), 4),
        "incoming_outgoing_count_ratio": _round(_safe_ratio(in_count, out_count), 4),
        "incoming_outgoing_amount_ratio": _round(_safe_ratio(in_total, out_total), 4),
        "net_flow_amount": round(in_total - out_total, 2),
        "turnover_amount": round(in_total + out_total, 2),
        "fan_in_ratio": _round(_safe_ratio(in_unique, in_count), 4),
        "fan_out_ratio": _round(_safe_ratio(out_unique, out_count), 4),
        "counterparty_diversity": _round(_safe_ratio(in_unique + out_unique, total_count), 4),
        "night_transaction_share": _round(_safe_ratio(night, total_count), 4),
        "weekend_transaction_share": _round(_safe_ratio(weekend, total_count), 4),
        "distinct_currencies": max(row.get("in_distinct_currencies") or 0, row.get("out_distinct_currencies") or 0),
        "distinct_payment_formats": max(row.get("in_distinct_formats") or 0, row.get("out_distinct_formats") or 0),
        "dominant_currency": currency.decode(row.get("dominant_currency")),
        "dominant_currency_share": _round(_safe_ratio(row.get("dominant_currency_count"), total_count), 4),
        "dominant_payment_format": payment_format.decode(row.get("dominant_format")),
        "dominant_payment_format_share": _round(_safe_ratio(row.get("dominant_format_count"), total_count), 4),
    }
    record.update(_pattern_flags(record))
    return record


def _pattern_flags(record: dict[str, Any]) -> dict[str, int]:
    """Coarse, rule-stated shape flags.

    These are deliberately simple and deliberately not the archetypes. Phase 3
    derives archetypes from the numeric features by clustering; these flags exist
    so a reviewer can sanity-check that the numbers describe recognizable
    behavior before any clustering is trusted. Each threshold is arbitrary and
    stated here rather than hidden in a config, because none of them is
    evidence-derived.
    """
    in_count = record["incoming_transaction_count"]
    out_count = record["outgoing_transaction_count"]
    total = record["transaction_count"]
    in_unique = record["unique_inbound_counterparties"]
    out_unique = record["unique_outbound_counterparties"]

    # Few inbound counterparties, regular receipts, outflow that follows inflow.
    salary_like = int(
        in_count >= 1
        and in_unique <= 2
        and out_count >= in_count
        and (record["incoming_outgoing_amount_ratio"] or 0) > 0.2
    )
    # Many distinct counterparties on both sides.
    business_like = int(in_unique >= 5 and out_unique >= 5)
    # Turnover far above the typical single payment: a conduit, not a wallet.
    median = record["median_incoming_amount"] or record["median_outgoing_amount"] or 0
    high_turnover = int(median > 0 and record["turnover_amount"] / median >= 100)
    low_frequency = int(total <= 3)

    return {
        "possible_salary_like_pattern": salary_like,
        "possible_business_like_pattern": business_like,
        "possible_high_turnover_pattern": high_turnover,
        "possible_low_frequency_pattern": low_frequency,
    }


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _write_csv(records: list[dict[str, Any]], output: Path) -> None:
    if not records:
        raise ValueError("no accounts were profiled")
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = list(records[0])
    table = pa.table({name: [record[name] for record in records] for name in columns})
    pacsv.write_csv(table, str(output), write_options=pacsv.WriteOptions(include_header=True))


def _summarize(
    records: list[dict[str, Any]],
    *,
    source: dict[str, Any],
    accounts_source: dict[str, Any] | None,
    meta: dict[str, Any],
    observed_days: int,
    epoch_day: int,
    started: datetime,
    truncated: bool,
) -> dict[str, Any]:
    numeric_columns = [
        "transaction_count",
        "turnover_amount",
        "unique_inbound_counterparties",
        "unique_outbound_counterparties",
        "active_days",
        "transactions_per_active_day",
        "median_incoming_amount",
        "median_outgoing_amount",
        "fan_in_ratio",
        "fan_out_ratio",
        "night_transaction_share",
    ]
    distributions = {}
    for name in numeric_columns:
        values = sorted(record[name] for record in records if record[name] is not None)
        if not values:
            continue
        distributions[name] = {
            "non_null": len(values),
            "min": values[0],
            "p25": values[len(values) // 4],
            "median": values[len(values) // 2],
            "p75": values[(3 * len(values)) // 4],
            "p95": values[min(len(values) - 1, (95 * len(values)) // 100)],
            "max": values[-1],
        }

    kinds: dict[str, int] = {}
    flags = dict.fromkeys(
        (
            "possible_salary_like_pattern",
            "possible_business_like_pattern",
            "possible_high_turnover_pattern",
            "possible_low_frequency_pattern",
        ),
        0,
    )
    formats: dict[str, int] = {}
    for record in records:
        key = record["entity_kind"] or "UNMATCHED"
        kinds[key] = kinds.get(key, 0) + 1
        for flag in flags:
            flags[flag] += record[flag]
        fmt = record["dominant_payment_format"] or "NONE"
        formats[fmt] = formats.get(fmt, 0) + 1

    return {
        "behavior_schema_version": BEHAVIOR_SCHEMA_VERSION,
        "profiled_at": started.isoformat(timespec="seconds"),
        "source": source,
        "accounts_source": accounts_source,
        "truncated_run": truncated,
        "transactions_read": meta["row_count"],
        "parse_failures": meta["parse_failures"],
        "accounts_profiled": len(records),
        "observation_window_days": observed_days,
        "first_observed_day": datetime.fromtimestamp(epoch_day * SECONDS_PER_DAY, UTC).date().isoformat(),
        "label_usage": {
            "is_laundering_read": False,
            "note": "The laundering column is dropped before any feature is computed.",
        },
        "entity_kind_counts": dict(sorted(kinds.items(), key=lambda item: -item[1])),
        "dominant_payment_format_counts": dict(sorted(formats.items(), key=lambda item: -item[1])),
        "pattern_flag_counts": flags,
        "distributions": distributions,
    }
