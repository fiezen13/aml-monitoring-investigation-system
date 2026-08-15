#!/usr/bin/env python3
"""Load any IBM AML *_Trans.csv into a DuckDB that benchmark_edge_level.py can read.

The Task-1 ETL (src/data/etl_transactions.py) does this in pandas, which is fine
for LI-Small but needs tens of GB for HI-Medium's 31.9M rows. This loader applies
the same column mapping, the same account-key rule, the same channel aliases and
the same FX table, but streams through DuckDB instead of materialising frames.

The currency and channel lookups are built from src.data.currency and
src.data.schemas, so they cannot drift from the main ETL.

Self-loop transactions (sender == receiver) are dropped, matching Task 1.

Usage:
  python scripts/load_ibm_dataset_duckdb.py \
    --csv data/raw/ibm-aml/HI-Medium_Trans.csv \
    --out data/processed/hi_medium.duckdb

  python scripts/benchmark_edge_level.py \
    --db data/processed/hi_medium.duckdb \
    --report-out reports/edge-benchmark/hi_medium.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.currency import FX_TO_USD, normalize_currency  # noqa: E402
from src.data.schemas import _CHANNEL_ALIASES, PaymentChannel  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True, help="IBM AML *_Trans.csv")
    p.add_argument("--out", type=Path, required=True, help="DuckDB file to create")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--memory-limit", default="6GB")
    return p.parse_args()


def _currency_lookup(con: duckdb.DuckDBPyConnection, csv_path: Path) -> None:
    """Build name -> USD rate from the currencies actually present in the file."""
    # One pass over the file: unnest both currency columns per row, then dedupe.
    names = (
        con.execute(
            "SELECT DISTINCT unnest(["
            '"Payment Currency", "Receiving Currency"]) AS c '
            f"FROM read_csv_auto('{csv_path.as_posix()}', header=true)"
        )
        .fetchdf()["c"]
        .dropna()
        .tolist()
    )

    rows = []
    unknown = []
    for name in names:
        try:
            rows.append({"name": name, "rate": FX_TO_USD[normalize_currency(name)]})
        except KeyError:
            unknown.append(name)
            rows.append({"name": name, "rate": 1.0})
    if unknown:
        print(f"[warn] no FX rate for {unknown}; treated as 1.0 USD", flush=True)
    con.register("fx_lookup", pd.DataFrame(rows))
    con.execute("CREATE OR REPLACE TABLE fx AS SELECT * FROM fx_lookup")


def _channel_lookup(con: duckdb.DuckDBPyConnection) -> None:
    rows = [{"raw": key, "channel": value.value} for key, value in _CHANNEL_ALIASES.items()]
    con.register("channel_lookup", pd.DataFrame(rows))
    con.execute("CREATE OR REPLACE TABLE channel_map AS SELECT * FROM channel_lookup")


def main() -> int:
    args = parse_args()
    if not args.csv.is_file():
        raise FileNotFoundError(args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise FileExistsError(f"{args.out} already exists; remove it first")

    started = time.perf_counter()
    con = duckdb.connect(str(args.out))
    con.execute("SET TimeZone='UTC'")
    con.execute(f"SET threads={int(args.threads)}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")

    print("[1/3] Reading currency and channel vocabularies ...", flush=True)
    _currency_lookup(con, args.csv)
    _channel_lookup(con)

    print("[2/3] Streaming the CSV into the transaction table ...", flush=True)
    csv = args.csv.as_posix()
    other = PaymentChannel.OTHER.value
    # The CSV repeats the header name "Account" for sender and receiver; DuckDB
    # disambiguates the second one as "Account_1".
    con.execute(
        f"""
        CREATE TABLE transaction AS
        WITH raw AS (
            SELECT
                row_number() OVER () AS row_ord,
                strptime("Timestamp", '%Y/%m/%d %H:%M') AT TIME ZONE 'UTC' AS occurred_at,
                "From Bank" AS from_bank_raw,
                CAST("Account" AS VARCHAR) AS from_account_raw,
                "To Bank" AS to_bank_raw,
                CAST("Account_1" AS VARCHAR) AS to_account_raw,
                CAST("Amount Paid" AS DOUBLE) AS amount_paid_orig,
                CAST("Payment Currency" AS VARCHAR) AS payment_currency,
                CAST("Amount Received" AS DOUBLE) AS amount_received_orig,
                CAST("Receiving Currency" AS VARCHAR) AS receiving_currency,
                CAST("Payment Format" AS VARCHAR) AS payment_format,
                CAST("Is Laundering" AS TINYINT) AS label_laundering
            -- keep Timestamp as text so the parse is ours, not the sniffer's
            FROM read_csv_auto('{csv}', header=true, types={{'Timestamp': 'VARCHAR'}})
        ),
        keyed AS (
            SELECT *,
                CASE WHEN regexp_full_match(trim(CAST(from_bank_raw AS VARCHAR)), '\\d+')
                     THEN CAST(CAST(trim(CAST(from_bank_raw AS VARCHAR)) AS BIGINT) AS VARCHAR)
                     ELSE trim(CAST(from_bank_raw AS VARCHAR)) END
                    || ':' || from_account_raw AS from_account_key,
                CASE WHEN regexp_full_match(trim(CAST(to_bank_raw AS VARCHAR)), '\\d+')
                     THEN CAST(CAST(trim(CAST(to_bank_raw AS VARCHAR)) AS BIGINT) AS VARCHAR)
                     ELSE trim(CAST(to_bank_raw AS VARCHAR)) END
                    || ':' || to_account_raw AS to_account_key
            FROM raw
        )
        SELECT
            md5(
                CAST(k.occurred_at AS VARCHAR) || '|' || k.from_account_key || '|' ||
                k.to_account_key || '|' || CAST(k.amount_paid_orig AS VARCHAR) || '|' ||
                k.payment_currency || '|' || CAST(k.row_ord AS VARCHAR)
            ) AS transaction_id,
            k.occurred_at,
            TRY_CAST(k.from_bank_raw AS BIGINT) AS from_bank,
            k.from_account_raw,
            k.from_account_key,
            TRY_CAST(k.to_bank_raw AS BIGINT) AS to_bank,
            k.to_account_raw,
            k.to_account_key,
            k.amount_paid_orig,
            k.payment_currency,
            k.amount_received_orig,
            k.receiving_currency,
            k.amount_paid_orig * COALESCE(fp.rate, 1.0) AS amount,
            k.amount_received_orig * COALESCE(fr.rate, 1.0) AS amount_received,
            'USD' AS currency,
            COALESCE(cm.channel, '{other}') AS channel,
            k.label_laundering
        FROM keyed k
        LEFT JOIN fx fp ON fp.name = k.payment_currency
        LEFT JOIN fx fr ON fr.name = k.receiving_currency
        LEFT JOIN channel_map cm ON cm.raw = upper(trim(k.payment_format))
        WHERE k.from_account_key <> k.to_account_key
        """
    )

    print("[3/3] Summary", flush=True)
    stats = con.execute(
        """
        SELECT count(*) AS rows, sum(label_laundering) AS laundering,
               min(occurred_at) AS first_ts, max(occurred_at) AS last_ts,
               count(DISTINCT from_account_key) AS senders
        FROM transaction
        """
    ).fetchdf()
    unmapped = con.execute("SELECT count(*) FROM transaction WHERE channel = ?", [other]).fetchone()[0]
    con.close()

    row = stats.iloc[0]
    rate = int(row["rows"] / row["laundering"]) if row["laundering"] else 0
    print(f"  transactions : {int(row['rows']):,} (self-loops dropped)")
    print(f"  laundering   : {int(row['laundering']):,}  (1 in {rate:,})")
    print(f"  period       : {row['first_ts']} .. {row['last_ts']}")
    print(f"  channel=OTHER: {unmapped:,}")
    print(f"  wrote {args.out} in {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
