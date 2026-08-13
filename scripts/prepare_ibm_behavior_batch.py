#!/usr/bin/env python3
"""Prepare an unlabeled canonical Behaviour batch from an IBM AML CSV.

This is a bounded adapter for the local PoC. It preserves identifier strings,
filters to one currency (so Behaviour amount features do not mix units), drops
self-loops rejected by the operational schema, and never writes the source
`Is Laundering` label to its output.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.aml import csvsource  # noqa: E402
from src.aml.schema import compute_transaction_id  # noqa: E402
from src.aml.transform import RowRejectedError, parse_amount, parse_timestamp  # noqa: E402

# Fixed so a given source file always yields the same batch.
_SELECTION_SEED = 20260728

OUTPUT_COLUMNS = (
    "transaction_id",
    "occurred_at",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount",
    "currency",
    "amount_received",
    "receiving_currency",
    "channel",
    "remarks",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10_000, help="Ceiling on rows written")
    parser.add_argument("--scan-limit", type=int, default=0, help="Source rows to scan; 0 scans the whole file")
    parser.add_argument(
        "--min-active-days",
        type=int,
        default=3,
        help="Keep only accounts transacting on at least this many distinct days",
    )
    parser.add_argument(
        "--min-transactions",
        type=int,
        default=20,
        help="Keep only accounts with at least this many transactions in the scanned range",
    )
    parser.add_argument("--currency-name", default="US Dollar")
    parser.add_argument("--currency-code", default="USD")
    return parser.parse_args(argv)


class _Accepted(NamedTuple):
    from_key: str
    to_key: str
    occurred_at: datetime


def _accept(
    values: list[str], *, currency_name: str, counters: Counter[str]
) -> _Accepted | None:
    """Apply the batch's admission rules to one source row.

    Shared by both passes so the account census counts exactly the rows the
    second pass is able to write; otherwise the projection drifts and the
    output lands short of the ceiling for no visible reason.
    """
    if len(values) != csvsource.COLUMN_COUNT:
        counters["invalid"] += 1
        return None

    from_bank = values[csvsource.COL_FROM_BANK].strip()
    from_account = values[csvsource.COL_FROM_ACCOUNT].strip()
    to_bank = values[csvsource.COL_TO_BANK].strip()
    to_account = values[csvsource.COL_TO_ACCOUNT].strip()
    if from_bank == to_bank and from_account == to_account:
        counters["self_loops"] += 1
        return None
    if (
        values[csvsource.COL_PAYMENT_CURRENCY].strip() != currency_name
        or values[csvsource.COL_RECEIVING_CURRENCY].strip() != currency_name
    ):
        counters["other_currency"] += 1
        return None
    try:
        occurred_at = parse_timestamp(values[csvsource.COL_TIMESTAMP])
        parse_amount(values[csvsource.COL_AMOUNT_PAID], "Amount Paid")
        parse_amount(values[csvsource.COL_AMOUNT_RECEIVED], "Amount Received")
    except RowRejectedError:
        counters["invalid"] += 1
        return None
    return _Accepted(f"{from_bank}:{from_account}", f"{to_bank}:{to_account}", occurred_at)


def select_accounts(
    source: Path,
    *,
    limit: int,
    scan_limit: int,
    min_active_days: int,
    min_transactions: int,
    currency_name: str,
) -> tuple[set[str], dict[str, int]]:
    """Census pass: choose whole accounts, never a prefix of the file.

    The IBM CSV is ordered by timestamp, so taking the first N rows takes the
    first N *minutes* — every account in the output then has a single active
    day and every duration feature (dwell time, inter-transaction gap, rapid
    forwarding) measures the slice rather than the account. Selecting accounts
    first and writing their whole history keeps each one's time series intact
    across the file's full span.
    """
    counts: Counter[str] = Counter()
    # Day ordinals rather than offsets from the first row seen: the IBM export
    # is broadly time-ordered but not strictly, and an offset scheme silently
    # discards any day earlier than the first one read.
    active_days: dict[str, set[int]] = {}
    counters: Counter[str] = Counter()
    scanned = 0

    for row in csvsource.iter_rows(source):
        scanned += 1
        if scan_limit and scanned > scan_limit:
            break
        accepted = _accept(row.values, currency_name=currency_name, counters=counters)
        if accepted is None:
            continue
        ordinal = accepted.occurred_at.date().toordinal()
        for key in (accepted.from_key, accepted.to_key):
            counts[key] += 1
            active_days.setdefault(key, set()).add(ordinal)

    eligible = [
        key
        for key, total in counts.items()
        if total >= min_transactions and len(active_days.get(key, ())) >= min_active_days
    ]
    # Sort for a stable order, then draw in a seeded shuffle. Taking the busiest
    # accounts first would spend the whole row budget on a few dozen of them and
    # leave the detector nothing to learn a normal range from; an unbiased draw
    # keeps the population's mix of volumes and yields far more accounts. The
    # seed is fixed, so the same input still produces the same batch.
    eligible.sort()
    random.Random(_SELECTION_SEED).shuffle(eligible)

    selected: set[str] = set()
    projected = 0
    for key in eligible:
        # Counting both endpoints double-counts rows between two selected
        # accounts, so this over-estimates and stops early rather than late.
        if projected + counts[key] > limit:
            continue
        selected.add(key)
        projected += counts[key]

    stats = {
        "scanned": scanned,
        "accounts_seen": len(counts),
        "accounts_eligible": len(eligible),
        "accounts_selected": len(selected),
        "days_covered": max((len(days) for days in active_days.values()), default=0),
    }
    return selected, stats


def prepare(
    source: Path,
    output: Path,
    *,
    limit: int,
    scan_limit: int,
    min_active_days: int,
    min_transactions: int,
    currency_name: str,
    currency_code: str,
) -> dict[str, int | str]:
    if limit < 5:
        raise ValueError("limit must be >= 5")
    if scan_limit and scan_limit < limit:
        raise ValueError("scan-limit must be >= limit, or 0 to scan the whole file")
    if min_active_days < 1:
        raise ValueError("min-active-days must be >= 1")
    if min_transactions < 1:
        raise ValueError("min-transactions must be >= 1")
    if not source.is_file():
        raise FileNotFoundError(source)
    code = currency_code.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("currency-code must be a three-letter ISO code")

    selected, census = select_accounts(
        source,
        limit=limit,
        scan_limit=scan_limit,
        min_active_days=min_active_days,
        min_transactions=min_transactions,
        currency_name=currency_name,
    )
    if not selected:
        raise RuntimeError(
            "no account met --min-active-days/--min-transactions; lower them or raise --scan-limit"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    # Only the selected accounts carry a complete history; their counterparties
    # appear in whatever rows happen to touch a subject. Scoring a counterparty
    # on that partial slice reproduces the clipped-window artefact one account
    # at a time, so downstream reads this manifest and scores subjects only.
    manifest = output.with_suffix(output.suffix + ".accounts.txt")
    manifest.write_text("\n".join(sorted(selected)) + "\n", encoding="utf-8")

    counters: Counter[str] = Counter()
    scanned = 0
    written = 0

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in csvsource.iter_rows(source):
            scanned += 1
            if (scan_limit and scanned > scan_limit) or written >= limit:
                break
            values = row.values
            accepted = _accept(values, currency_name=currency_name, counters=counters)
            if accepted is None:
                continue
            if accepted.from_key not in selected and accepted.to_key not in selected:
                counters["unselected_account"] += 1
                continue

            from_bank = values[csvsource.COL_FROM_BANK].strip()
            from_account = values[csvsource.COL_FROM_ACCOUNT].strip()
            to_bank = values[csvsource.COL_TO_BANK].strip()
            to_account = values[csvsource.COL_TO_ACCOUNT].strip()
            occurred_at = accepted.occurred_at.isoformat(timespec="seconds") + "Z"
            amount = parse_amount(values[csvsource.COL_AMOUNT_PAID], "Amount Paid")
            amount_received = parse_amount(values[csvsource.COL_AMOUNT_RECEIVED], "Amount Received")

            source_id = compute_transaction_id(
                source_file=source.name,
                source_line_number=row.line_number,
                timestamp_raw=values[csvsource.COL_TIMESTAMP].strip(),
                from_bank=from_bank,
                from_account=from_account,
                to_bank=to_bank,
                to_account=to_account,
                amount_received_raw=values[csvsource.COL_AMOUNT_RECEIVED].strip(),
                amount_paid_raw=values[csvsource.COL_AMOUNT_PAID].strip(),
            )
            writer.writerow(
                {
                    "transaction_id": source_id,
                    "occurred_at": occurred_at,
                    "from_bank": from_bank,
                    "from_account": from_account,
                    "to_bank": to_bank,
                    "to_account": to_account,
                    "amount": str(amount),
                    "currency": code,
                    "amount_received": str(amount_received),
                    "receiving_currency": code,
                    "channel": values[csvsource.COL_PAYMENT_FORMAT].strip(),
                    "remarks": "",
                }
            )
            written += 1

    # `limit` is a ceiling, not a target: the last account is admitted whole or
    # not at all, because truncating one mid-history reintroduces exactly the
    # clipped time series this selection exists to avoid.
    return {
        "input": str(source),
        "output": str(output),
        "subject_accounts_manifest": str(manifest),
        "scanned": scanned,
        "written": written,
        "self_loops_skipped": counters["self_loops"],
        "other_currency_skipped": counters["other_currency"],
        "invalid_skipped": counters["invalid"],
        "unselected_account_skipped": counters["unselected_account"],
        "accounts_seen": census["accounts_seen"],
        "accounts_eligible": census["accounts_eligible"],
        "accounts_selected": census["accounts_selected"],
        "max_active_days": census["days_covered"],
        "labels_written": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = prepare(
        args.input,
        args.output,
        limit=args.limit,
        scan_limit=args.scan_limit,
        min_active_days=args.min_active_days,
        min_transactions=args.min_transactions,
        currency_name=args.currency_name,
        currency_code=args.currency_code,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
