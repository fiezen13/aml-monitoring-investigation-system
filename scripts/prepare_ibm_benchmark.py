#!/usr/bin/env python3
"""Build a labelled DuckDB for benchmarking the Behaviour model.

Separate from `prepare_ibm_behavior_batch.py` on purpose. That script feeds the
operational pipeline and must never emit `Is Laundering`; this one exists only
to score a model that has already been trained without labels, so it keeps the
ground truth in a table the feature job does not read.

The account selection is shared with the operational prep, so a benchmark run
measures the same population shape the pipeline actually sees — whole account
histories across the file's full span, never a prefix of it.

    python scripts/prepare_ibm_benchmark.py \\
        --input data/raw/ibm-aml/LI-Small_Trans.csv \\
        --output data/processed/aml.duckdb --limit 400000
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_ibm_behavior_batch import _accept, select_accounts  # noqa: E402
from src.aml import csvsource  # noqa: E402
from src.aml.transform import parse_amount  # noqa: E402

TRAIN_FRACTION = 0.60
VAL_FRACTION = 0.80


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/aml.duckdb")
    parser.add_argument("--limit", type=int, default=400_000, help="Ceiling on rows written")
    parser.add_argument("--scan-limit", type=int, default=0, help="Source rows to scan; 0 scans the whole file")
    parser.add_argument("--min-active-days", type=int, default=3)
    parser.add_argument("--min-transactions", type=int, default=20)
    parser.add_argument("--currency-name", default="US Dollar")
    return parser.parse_args(argv)


def _split_of(index: int, total: int) -> str:
    """Chronological 60/20/20, matching the operational batch's split policy."""
    if index < int(total * TRAIN_FRACTION):
        return "train"
    if index < int(total * VAL_FRACTION):
        return "val"
    return "test"


def build(
    source: Path,
    output: Path,
    *,
    limit: int,
    scan_limit: int,
    min_active_days: int,
    min_transactions: int,
    currency_name: str,
) -> dict[str, object]:
    if not source.is_file():
        raise FileNotFoundError(source)

    selected, census = select_accounts(
        source,
        limit=limit,
        scan_limit=scan_limit,
        min_active_days=min_active_days,
        min_transactions=min_transactions,
        currency_name=currency_name,
    )
    if not selected:
        raise RuntimeError("no account met the history thresholds; lower them or raise --scan-limit")

    counters: Counter[str] = Counter()
    rows: list[tuple[object, ...]] = []
    scanned = 0
    for row in csvsource.iter_rows(source):
        scanned += 1
        if (scan_limit and scanned > scan_limit) or len(rows) >= limit:
            break
        values = row.values
        accepted = _accept(values, currency_name=currency_name, counters=counters)
        if accepted is None:
            continue
        if accepted.from_key not in selected and accepted.to_key not in selected:
            continue
        rows.append(
            (
                accepted.occurred_at,
                accepted.from_key,
                accepted.to_key,
                float(parse_amount(values[csvsource.COL_AMOUNT_PAID], "Amount Paid")),
                1 if values[csvsource.COL_IS_LAUNDERING].strip() == "1" else 0,
            )
        )

    # Sort by time before splitting: the split must be chronological, and the
    # source file is only broadly ordered.
    rows.sort(key=lambda item: item[0])
    total = len(rows)
    rows = [(*item, _split_of(index, total)) for index, item in enumerate(rows)]

    output.parent.mkdir(parents=True, exist_ok=True)
    # Same manifest the operational batch uses to decide what gets scored. A
    # benchmark that also scores the thin counterparties measures a population
    # production never alerts on, and its precision is not comparable.
    manifest = output.with_suffix(output.suffix + ".accounts.txt")
    manifest.write_text("\n".join(sorted(selected)) + "\n", encoding="utf-8")
    if output.exists():
        output.unlink()
    connection = duckdb.connect(str(output))
    try:
        connection.execute(
            """CREATE TABLE transaction (
                   occurred_at TIMESTAMPTZ NOT NULL,
                   from_account_key VARCHAR NOT NULL,
                   to_account_key VARCHAR NOT NULL,
                   amount DOUBLE NOT NULL,
                   label_laundering INTEGER NOT NULL,
                   split VARCHAR NOT NULL
               )"""
        )
        connection.executemany("INSERT INTO transaction VALUES (?, ?, ?, ?, ?, ?)", rows)
        connection.execute("CREATE INDEX tx_time_idx ON transaction(occurred_at)")
        connection.execute("CREATE INDEX tx_from_idx ON transaction(from_account_key, occurred_at)")
        connection.execute("CREATE INDEX tx_to_idx ON transaction(to_account_key, occurred_at)")
        connection.execute("CREATE INDEX tx_split_idx ON transaction(split)")
        by_split = dict(
            connection.execute("SELECT split, count(*) FROM transaction GROUP BY split").fetchall()
        )
        positives = int(connection.execute("SELECT sum(label_laundering) FROM transaction").fetchone()[0] or 0)
        positive_accounts = int(
            connection.execute(
                """SELECT count(DISTINCT account_key) FROM (
                       SELECT from_account_key AS account_key FROM transaction WHERE label_laundering = 1
                       UNION
                       SELECT to_account_key FROM transaction WHERE label_laundering = 1
                   )"""
            ).fetchone()[0]
            or 0
        )
    finally:
        connection.close()

    return {
        "input": str(source),
        "output": str(output),
        "subject_accounts_manifest": str(manifest),
        "rows": total,
        "rows_by_split": by_split,
        "labelled_transactions": positives,
        "labelled_accounts": positive_accounts,
        "accounts_selected": census["accounts_selected"],
        "accounts_eligible": census["accounts_eligible"],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build(
        args.input,
        args.output,
        limit=args.limit,
        scan_limit=args.scan_limit,
        min_active_days=args.min_active_days,
        min_transactions=args.min_transactions,
        currency_name=args.currency_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
