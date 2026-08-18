#!/usr/bin/env python3
"""Dựng dân số HI-Medium trong một cơ sở dữ liệu riêng, để nạp được cảnh báo MEGA-PNA.

    createdb fin07_hi_medium && psql -f db/init/*.sql
    python scripts/load_hi_medium_population.py --database-url postgresql://.../fin07_hi_medium

Vì sao cần
----------
``alert.account_key`` có khoá ngoại tới ``account``. Cảnh báo MEGA-PNA trỏ tới
tài khoản **HI-Medium**, trong khi cơ sở dữ liệu hiện có chỉ chứa dân số
**LI-Small** — 576.781 tài khoản, không tài khoản nào trùng. Khoá ngoại chặn
thẳng, nên phải dựng dân số trước.

Phạm vi: chỉ cửa sổ TEST
------------------------
Nạp cả 29,3 triệu giao dịch là ~15 GB và không cần thiết. Cảnh báo sinh từ tập
test, nên chỉ nạp giao dịch trong cửa sổ test cộng 7 ngày nhìn lại — đủ để mọi
cảnh báo mở được sổ giao dịch, mọi phiên điều tra tra được lân cận, và trang tra
cứu có nội dung.

KYC không có trong dữ liệu
--------------------------
Bộ IBM AML chỉ có 11 cột: thời điểm, ngân hàng và tài khoản hai đầu, số tiền,
loại tiền, hình thức, cờ nhãn. Không nghề nghiệp, không thu nhập, không quốc gia.
Các trường ấy được ghi thẳng là ``kyc_unavailable`` chứ **không bịa** — bịa ra
một hồ sơ KYC rồi để mô hình phát hiện lại chính nó là lỗi đã mắc với R03/R04.
"""

from __future__ import annotations

import argparse
import gzip
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB = ROOT / "data/processed/aml_hi_medium.duckdb"
#: Cửa sổ test bắt đầu 14/09; lùi 7 ngày để cảnh báo có đủ lịch sử tra cứu.
DEFAULT_FROM = "2022-09-07"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--database-url", required=True)
    p.add_argument("--from-date", default=DEFAULT_FROM)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--memory-limit", default="12GB")
    return p.parse_args(argv)


def _pg_url(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


def _copy_gzip(pg: psycopg.Connection[Any], statement: str, path: Path) -> int:
    total = 0
    with pg.cursor().copy(statement) as copy, gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            copy.write(line)
            total += 1
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.db.is_file():
        raise FileNotFoundError(args.db)

    duck = duckdb.connect(str(args.db), read_only=True)
    duck.execute("SET TimeZone='UTC'")
    duck.execute(f"SET threads={int(args.threads)}")
    duck.execute(f"SET memory_limit='{args.memory_limit}'")

    tmp = Path(tempfile.mkdtemp(prefix="fin07-himedium-"))
    accounts_csv = tmp / "accounts.csv.gz"
    tx_csv = tmp / "transactions.csv.gz"

    print(f"[1/4] Trích tài khoản và giao dịch từ {args.from_date} ...", flush=True)
    duck.execute(
        f"""
        COPY (
          WITH scoped AS (
            SELECT * FROM "transaction" WHERE occurred_at >= DATE '{args.from_date}'
          ), keys AS (
            SELECT DISTINCT from_account_key AS account_key FROM scoped
            UNION
            SELECT DISTINCT to_account_key FROM scoped
          )
          SELECT account_key,
                 'CUS-' || md5(account_key)                AS customer_id,
                 split_part(account_key, ':', 1)           AS bank_code,
                 split_part(account_key, ':', 2)           AS account_number,
                 DATE '{args.from_date}'                   AS opened_at
            FROM keys
        ) TO '{accounts_csv.as_posix()}' (FORMAT CSV, HEADER false, COMPRESSION GZIP)
        """
    )
    duck.execute(
        f"""
        COPY (
          -- Giữ nguyên đơn vị gốc, không quy đổi USD: đây là thiết kế
          -- currency-native, và migration 013 ghi rõ "keep the source units
          -- verbatim". DuckDB có cả hai — `amount` đã quy đổi USD và
          -- `amount_paid_orig` là số tiền thật — nên phải lấy đúng cột sau.
          SELECT transaction_id AS source_transaction_id, occurred_at,
                 from_account_key, to_account_key,
                 amount_paid_orig AS amount, payment_currency AS currency,
                 amount_received_orig AS amount_received,
                 receiving_currency, channel
            FROM "transaction" WHERE occurred_at >= DATE '{args.from_date}'
        ) TO '{tx_csv.as_posix()}' (FORMAT CSV, HEADER false, COMPRESSION GZIP)
        """
    )
    banks = duck.execute(
        f"""SELECT DISTINCT split_part(k, ':', 1) FROM (
              SELECT from_account_key k FROM "transaction" WHERE occurred_at >= DATE '{args.from_date}'
              UNION SELECT to_account_key FROM "transaction" WHERE occurred_at >= DATE '{args.from_date}')"""
    ).fetchall()
    duck.close()
    print(f"      {len(banks):,} ngân hàng", flush=True)

    with psycopg.connect(_pg_url(args.database_url)) as pg:
        print("[2/4] Nạp ngân hàng ...", flush=True)
        with pg.cursor().copy("COPY bank (bank_code, bank_name, country_source) FROM STDIN WITH (FORMAT CSV)") as copy:
            for (code,) in banks:
                # 'unknown' là giá trị hợp lệ duy nhất cho "không đọc được từ dữ
                # liệu". Bộ IBM AML không có cột quốc gia; gán 'assigned' sẽ lặp lại
                # đúng lỗi của R04 — dự án tự gán rồi tự phát hiện lại.
                copy.write(f'{code},"Bank {code}",unknown\n')

        print("[3/4] Nạp khách hàng và tài khoản ...", flush=True)
        pg.execute(
            """CREATE TEMP TABLE stage_account (
                 account_key TEXT, customer_id TEXT, bank_code TEXT,
                 account_number TEXT, opened_at DATE)"""
        )
        n_acc = _copy_gzip(pg, "COPY stage_account FROM STDIN WITH (FORMAT CSV)", accounts_csv)
        pg.execute(
            """INSERT INTO customer (customer_id, customer_type, prototype, occupation,
                                     declared_income_band, expected_monthly_volume,
                                     registered_country, onboarding_date, risk_rating)
               SELECT customer_id, 'organisation', 'enterprise',
                      'KYC unavailable - IBM AML HI-Medium', 'kyc_unavailable',
                      0, 'XX', opened_at, 'medium'
                 FROM stage_account
               ON CONFLICT (customer_id) DO NOTHING"""
        )
        pg.execute(
            """INSERT INTO account (account_key, customer_id, bank_code, account_number, opened_at, status)
               SELECT account_key, customer_id, bank_code, account_number, opened_at, 'active'
                 FROM stage_account
               ON CONFLICT (account_key) DO NOTHING"""
        )
        pg.commit()

        print("[4/4] Nạp giao dịch ...", flush=True)
        pg.execute(
            """CREATE TEMP TABLE stage_tx (
                 source_transaction_id TEXT, occurred_at TIMESTAMPTZ,
                 from_account_key TEXT, to_account_key TEXT, amount NUMERIC,
                 currency TEXT, amount_received NUMERIC, receiving_currency TEXT,
                 channel TEXT)"""
        )
        n_tx = _copy_gzip(pg, "COPY stage_tx FROM STDIN WITH (FORMAT CSV)", tx_csv)
        pg.execute(
            """INSERT INTO transaction (source_transaction_id, occurred_at, from_account_key,
                                        to_account_key, amount, currency, amount_received,
                                        receiving_currency, channel, dataset_split,
                                        source_dataset, source_file, ingested_at)
               -- Chia tập theo đúng mốc của lần huấn luyện MEGA-PNA: validation
               -- kết thúc 14/09, test từ đó trở đi. Ghi vào cột này để mọi truy
               -- vấn sau biết dòng nào thuộc tập nào mà không phải suy lại.
               SELECT source_transaction_id, occurred_at, from_account_key, to_account_key,
                      amount, currency, amount_received, receiving_currency, channel,
                      CASE WHEN occurred_at < TIMESTAMPTZ '2022-09-14' THEN 'validation' ELSE 'test' END,
                      'IBM AML HI-Medium', 'HI-Medium_Trans.csv', now()
                 FROM stage_tx
               ON CONFLICT DO NOTHING"""
        )
        pg.commit()
        counts = pg.execute(
            """SELECT (SELECT count(*) FROM bank), (SELECT count(*) FROM account),
                      (SELECT count(*) FROM transaction)"""
        ).fetchone()

    accounts_csv.unlink(missing_ok=True)
    tx_csv.unlink(missing_ok=True)
    print(f"\nđã nạp: {counts[0]:,} ngân hàng · {counts[1]:,} tài khoản · {counts[2]:,} giao dịch")
    print(f"(staging đọc {n_acc:,} dòng tài khoản, {n_tx:,} dòng giao dịch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
