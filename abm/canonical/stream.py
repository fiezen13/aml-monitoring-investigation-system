"""Stream the transaction tables to CSV with bounded memory.

The small release held every transaction as a Python dict in a list, which is
fine for 461,537 rows and impossible for 31,898,238: a dict per row costs on the
order of a kilobyte, so the full release would need tens of gigabytes to write a
six-gigabyte file.

This module writes rows as it computes them. Memory is bounded by one chunk plus
the per-account arrays, so the full release costs about the same as the small one.

Three consequences shaped the design:

- **Account state is columnar, not a dict of dicts.** Scale factor, digital
  segment, and international exposure live in parallel numpy arrays indexed by
  account position. 2.08 million accounts cost about 40 MB this way against
  roughly 2 GB as dicts.
- **Key lookup is vectorised.** `pc.index_in` maps 63.8 million endpoint keys to
  positions in one call instead of 63.8 million Python dict lookups.
- **The scenario join is inverted.** Rather than indexing every transaction so
  patterns can find theirs, only the 4,086 pattern transactions are indexed and
  each row checks itself against that small map.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from abm.canonical.transactions import (
    ASSUME_CHANNEL_BY_FORMAT,
    ASSUME_CHANNEL_MIX,
    COUNTERPARTY_ID_FORMAT,
    SCHEMA_VERSION,
    TRANSACTION_ID_FORMAT,
    event_id,
    format_timestamp,
)

SECONDS_PER_DAY = 86_400

# Rows processed per pass. Large enough that per-chunk overhead disappears,
# small enough that a chunk's temporaries stay well inside a gigabyte.
CHUNK_ROWS = 1_000_000

DIGITAL_SEGMENTS = ("NONE", "LOW", "MEDIUM", "HIGH")


class AccountColumns:
    """Per-account state in parallel arrays, indexed by position."""

    __slots__ = ("keys", "index", "account_ids", "scale", "digital", "international")

    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        ordered = sorted(accounts, key=lambda account: account["_key"])
        self.keys = pa.array([account["_key"] for account in ordered], pa.string())
        self.account_ids = [account["account_id"] for account in ordered]
        self.scale = np.array(
            [account["_scale"] if account["_scale"] is not None else np.nan for account in ordered],
            dtype=np.float64,
        )
        segment_code = {name: index for index, name in enumerate(DIGITAL_SEGMENTS)}
        self.digital = np.array(
            [segment_code.get(account["_entity"].get("digital_usage_segment") or "NONE", 0) for account in ordered],
            dtype=np.int8,
        )
        self.international = np.array(
            [
                bool(
                    account["_entity"].get("domestic_international_profile") in ("MIXED", "INTERNATIONAL_HEAVY")
                    or account["_entity"].get("income_band") == "Q5"
                )
                for account in ordered
            ],
            dtype=bool,
        )

    def positions(self, keys: pa.Array) -> np.ndarray:
        """Map account keys to positions; -1 where the key is external."""
        found = pc.index_in(keys, value_set=self.keys)
        return pc.fill_null(found, -1).to_numpy(zero_copy_only=False).astype(np.int64)


def _cumulative(weights: dict[str, float]) -> tuple[list[str], np.ndarray]:
    names = list(weights)
    probabilities = np.array([weights[name] for name in names], dtype=float)
    return names, np.cumsum(probabilities / probabilities.sum())


_FORMAT_TABLE = {segment: _cumulative(mix) for segment, mix in ASSUME_CHANNEL_MIX.items()}
_CHANNEL_TABLE = {payment_format: _cumulative(mix) for payment_format, mix in ASSUME_CHANNEL_BY_FORMAT.items()}


def _draw(table: tuple[list[str], np.ndarray], draws: np.ndarray) -> np.ndarray:
    names, cumulative = table
    picks = np.searchsorted(cumulative, draws, side="right")
    np.clip(picks, 0, len(names) - 1, out=picks)
    return np.array(names, dtype=object)[picks]


def redraw_times_chunked(stamps: np.ndarray, rng: np.random.Generator, profile: np.ndarray) -> np.ndarray:
    """Vectorised time-of-day redraw preserving date and global ordering."""
    days = stamps // SECONDS_PER_DAY
    rebuilt = np.empty_like(stamps)
    probabilities = profile / profile.sum()

    for day in np.unique(days):
        mask = days == day
        count = int(mask.sum())
        hours = rng.choice(24, size=count, p=probabilities)
        seconds = np.sort(hours * 3600 + rng.integers(0, 3600, size=count))
        order = np.argsort(stamps[mask], kind="stable")
        slot = np.empty(count, dtype=np.int64)
        slot[order] = seconds
        rebuilt[mask] = day * SECONDS_PER_DAY + slot
    return rebuilt


def stream_transactions(
    *,
    raw: pa.Table,
    columns: AccountColumns,
    pattern_lookup: dict[tuple[int, int, int], tuple[str, str]],
    transactions_path: Path,
    labels_path: Path,
    transaction_columns: list[str],
    label_columns: list[str],
    merchant_ids: list[str],
    diurnal_profile: np.ndarray,
    international_wire_share: float,
    rng: np.random.Generator,
    time_partition: Any,
) -> dict[str, Any]:
    """Write both transaction tables in one pass over the sorted rows."""
    from_positions = columns.positions(raw.column("from_key").combine_chunks())
    to_positions = columns.positions(raw.column("to_key").combine_chunks())
    stamps = raw.column("timestamp_epoch").to_numpy(zero_copy_only=False).astype(np.int64)
    amounts = raw.column("amount").to_numpy(zero_copy_only=False)
    labels = raw.column("is_laundering").to_numpy(zero_copy_only=False)

    rebuilt = redraw_times_chunked(stamps, rng, diurnal_profile)
    order = np.argsort(stamps, kind="stable")

    first_day = int(stamps.min() // SECONDS_PER_DAY)
    last_day = int(stamps.max() // SECONDS_PER_DAY)

    from_keys = raw.column("from_key").combine_chunks()
    to_keys = raw.column("to_key").combine_chunks()

    tokens: dict[str, str] = {}
    flagged_accounts: set[str] = set()
    written = 0
    scenario_matches = 0
    label_counts = {0: 0, 1: 0}

    transactions_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        transactions_path.open("w", encoding="utf-8", newline="") as tx_handle,
        labels_path.open("w", encoding="utf-8", newline="") as label_handle,
    ):
        tx_writer = csv.writer(tx_handle, lineterminator="\n")
        label_writer = csv.writer(label_handle, lineterminator="\n")
        tx_writer.writerow(transaction_columns)
        label_writer.writerow(label_columns)

        for start in range(0, len(order), CHUNK_ROWS):
            slice_index = order[start : start + CHUNK_ROWS]
            size = len(slice_index)

            source_position = from_positions[slice_index]
            target_position = to_positions[slice_index]
            source_internal = source_position >= 0
            target_internal = target_position >= 0

            source_scale = np.where(source_internal, columns.scale[source_position], np.nan)
            target_scale = np.where(target_internal, columns.scale[target_position], np.nan)
            scale = _geometric_mean(source_scale, target_scale)

            chunk_amounts = np.rint(amounts[slice_index] * scale)
            usable = np.isfinite(scale) & np.isfinite(chunk_amounts)
            chunk_amounts = np.where(usable, np.maximum(chunk_amounts, 1.0), 0.0)

            # Digital segment comes from whichever endpoint the bank owns.
            segment_code = np.where(
                source_internal,
                columns.digital[np.where(source_internal, source_position, 0)],
                np.where(target_internal, columns.digital[np.where(target_internal, target_position, 0)], 0),
            )
            exposed = np.where(
                source_internal,
                columns.international[np.where(source_internal, source_position, 0)],
                np.where(
                    target_internal,
                    columns.international[np.where(target_internal, target_position, 0)],
                    False,
                ),
            )
            external = ~(source_internal & target_internal)

            format_draws = rng.random(size)
            formats = np.empty(size, dtype=object)
            for code, segment in enumerate(DIGITAL_SEGMENTS):
                mask = segment_code == code
                if mask.any():
                    formats[mask] = _draw(_FORMAT_TABLE[segment], format_draws[mask])

            wire = exposed & external & (rng.random(size) < international_wire_share)
            formats[wire] = "INTERNATIONAL_WIRE"

            channel_draws = rng.random(size)
            channels = np.empty(size, dtype=object)
            for payment_format, table in _CHANNEL_TABLE.items():
                mask = formats == payment_format
                if mask.any():
                    channels[mask] = _draw(table, channel_draws[mask])

            merchant_draws = (
                rng.integers(0, len(merchant_ids), size=size) if merchant_ids else np.zeros(size, dtype=np.int64)
            )
            salary_draws = rng.random(size)

            chunk_from = from_keys.take(pa.array(slice_index)).to_pylist()
            chunk_to = to_keys.take(pa.array(slice_index)).to_pylist()
            chunk_times = rebuilt[slice_index]
            chunk_stamps = stamps[slice_index]
            chunk_labels = labels[slice_index]

            for position in range(size):
                if not usable[position]:
                    continue
                amount = int(chunk_amounts[position])
                written += 1
                transaction_id = TRANSACTION_ID_FORMAT.format(written)

                source_id = columns.account_ids[source_position[position]] if source_internal[position] else None
                target_id = columns.account_ids[target_position[position]] if target_internal[position] else None
                source_token = None if source_id else _token(tokens, chunk_from[position])
                target_token = None if target_id else _token(tokens, chunk_to[position])

                payment_format = formats[position]
                merchant = (
                    merchant_ids[int(merchant_draws[position])]
                    if merchant_ids and payment_format in ("CARD_PAYMENT", "QR_PAYMENT")
                    else None
                )
                if merchant:
                    transaction_type = "PURCHASE"
                elif payment_format == "CASH_DEPOSIT":
                    transaction_type = "DEPOSIT"
                elif payment_format == "CASH_WITHDRAWAL":
                    transaction_type = "WITHDRAWAL"
                elif payment_format == "INTERBANK_TRANSFER" and salary_draws[position] < 0.02:
                    transaction_type = "SALARY"
                else:
                    transaction_type = "TRANSFER"

                epoch = int(chunk_times[position])
                amount_text = str(amount)
                tx_writer.writerow(
                    [
                        transaction_id,
                        event_id(
                            transaction_id,
                            source_id or source_token or "",
                            target_id or target_token or "",
                            epoch,
                            amount_text,
                        ),
                        SCHEMA_VERSION,
                        format_timestamp(epoch),
                        source_id or "",
                        target_id or "",
                        source_token or "",
                        target_token or "",
                        amount_text,
                        "VND",
                        payment_format,
                        channels[position],
                        transaction_type,
                        merchant or "",
                        time_partition(epoch // SECONDS_PER_DAY, first_day, last_day),
                    ]
                )

                label = int(chunk_labels[position])
                label_counts[label] = label_counts.get(label, 0) + 1
                scenario = pattern_lookup.get(
                    (
                        int(from_positions[slice_index[position]]),
                        int(to_positions[slice_index[position]]),
                        int(chunk_stamps[position]),
                    )
                )
                if scenario is not None:
                    scenario_matches += 1
                label_writer.writerow(
                    [
                        transaction_id,
                        label,
                        scenario[0] if scenario else "",
                        scenario[1] if scenario else "",
                        "IBM_PATTERNS" if scenario else "IBM_AML",
                    ]
                )

                if label == 1:
                    if source_id:
                        flagged_accounts.add(source_id)
                    if target_id:
                        flagged_accounts.add(target_id)

    return {
        "written": written,
        "flagged_accounts": flagged_accounts,
        "external_counterparties": len(tokens),
        "scenario_matches": scenario_matches,
        "label_counts": label_counts,
        "first_day": first_day,
        "last_day": last_day,
        "window_start": format_timestamp(int(stamps.min())),
        "window_end": format_timestamp(int(stamps.max())),
    }


def _geometric_mean(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Geometric mean where both sides exist, otherwise whichever one does."""
    both = np.isfinite(first) & np.isfinite(second)
    only_first = np.isfinite(first) & ~np.isfinite(second)
    only_second = ~np.isfinite(first) & np.isfinite(second)

    result = np.full(len(first), np.nan)
    result[both] = np.sqrt(first[both] * second[both])
    result[only_first] = first[only_first]
    result[only_second] = second[only_second]
    return result


def _token(tokens: dict[str, str], key: str) -> str:
    existing = tokens.get(key)
    if existing is None:
        existing = COUNTERPARTY_ID_FORMAT.format(len(tokens) + 1)
        tokens[key] = existing
    return existing


def append_hard_negative_transactions(
    *,
    episodes: list[Any],
    account_lookup: dict[str, dict[str, Any]],
    transactions_path: Path,
    labels_path: Path,
    offset: int,
    first_day: int,
    last_day: int,
    rng: np.random.Generator,
    time_partition: Any,
) -> int:
    """Append hard-negative legs; IBM rows are never rewritten."""
    written = 0
    with (
        transactions_path.open("a", encoding="utf-8", newline="") as tx_handle,
        labels_path.open("a", encoding="utf-8", newline="") as label_handle,
    ):
        tx_writer = csv.writer(tx_handle, lineterminator="\n")
        label_writer = csv.writer(label_handle, lineterminator="\n")

        for episode in episodes:
            account = account_lookup.get(episode.account_id)
            if account is None:
                continue
            segment = account["_entity"].get("digital_usage_segment") or "NONE"
            digital = segment in ("HIGH", "MEDIUM")
            for leg in episode.legs:
                written += 1
                position = offset + written
                transaction_id = TRANSACTION_ID_FORMAT.format(position)
                epoch = int(leg["day"]) * SECONDS_PER_DAY + int(rng.integers(6 * 3600, 21 * 3600))
                token = COUNTERPARTY_ID_FORMAT.format(900_000 + (position % 90_000))
                amount = str(max(int(round(leg["amount_vnd"])), 1000))

                tx_writer.writerow(
                    [
                        transaction_id,
                        event_id(transaction_id, token, episode.account_id, epoch, amount),
                        SCHEMA_VERSION,
                        format_timestamp(epoch),
                        "" if leg["inbound"] else episode.account_id,
                        episode.account_id if leg["inbound"] else "",
                        token if leg["inbound"] else "",
                        "" if leg["inbound"] else token,
                        amount,
                        "VND",
                        "INTERBANK_TRANSFER" if digital else "CASH_DEPOSIT",
                        "MOBILE" if digital else "BRANCH",
                        "TRANSFER",
                        "",
                        time_partition(leg["day"], first_day, last_day),
                    ]
                )
                label_writer.writerow([transaction_id, 0, "", "", "P022_SIMULATION"])
    return written
