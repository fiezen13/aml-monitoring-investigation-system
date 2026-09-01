#!/usr/bin/env python3
"""Nạp bổ sung cửa sổ giao dịch HI-Medium còn thiếu.

    python scripts/backfill_hi_medium_window.py --to-date 2022-09-07

Vì sao cần
----------
``load_hi_medium_population.py`` cố ý chỉ nạp từ 07/09 — cửa sổ test cộng 7 ngày
nhìn lại — để tiết kiệm dung lượng. Quyết định ấy đúng cho việc mở sổ giao dịch
của một cảnh báo, nhưng nó cắt mất 13,4 triệu giao dịch đầu kỳ.

Hậu quả chỉ lộ ra khi đi tìm mẫu hình: 493 vụ rửa tiền mà IBM gắn nhãn diễn ra
từ 01/09 đến 14/09, nên phần lớn nằm TRƯỚC mốc nạp. Đo được: không một vụ nào
còn đủ cạnh trong cơ sở dữ liệu — chu trình còn trung bình 17,8% số cạnh,
BIPARTITE còn 0%. Một vòng khép kín thiếu một cạnh thì không còn là vòng, nên
không bộ dò nào tìm ra được, kể cả bộ dò hoàn hảo.

Vì sao là script riêng chứ không thêm cờ vào bộ nạp cũ
------------------------------------------------------
Bộ nạp cũ COPY thẳng vào ``bank`` và hỏng ngay khi chạy lần hai vì trùng khoá.
Nó được viết cho một lần dựng cơ sở dữ liệu trắng. Script này chỉ làm phần bổ
sung và chịu được chạy lại nhiều lần.

Nhãn tập dữ liệu
----------------
Mốc chia của lần huấn luyện MEGA-PNA tính theo NGÀY kể từ 01/09: train là ngày
0-8, validation 9-12, test 13 trở đi. Bộ nạp cũ ghi mọi dòng trước 14/09 là
``validation`` — đúng với phần nó nạp (từ 07/09), nhưng sai với phần đầu kỳ.
Ở đây ghi đúng: trước 10/09 là ``train``.
"""

from __future__ import annotations

import argparse
import gzip
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/processed/aml_hi_medium.duckdb"
TRAIN_END = "2022-09-10"  # ngày 9 bắt đầu validation


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--to-date", default="2022-09-07", help="nạp các giao dịch TRƯỚC mốc này")
    p.add_argument("--container", default="fin07-postgres-1")
    p.add_argument("--database", default="fin07_hi_medium")
    p.add_argument("--db-user", default="fin07")
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--memory-limit", default="8GB")
    return p.parse_args()


def sql(args: argparse.Namespace, statement: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            args.database,
            "-tAc",
            statement,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        print(proc.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout.strip()


def copy_gzip(args: argparse.Namespace, statement: str, path: Path) -> int:
    """Giải nén rồi bơm từng dòng vào psql qua stdin.

    Không truyền thẳng đối tượng gzip vào ``stdin=``: subprocess lấy file
    descriptor của tệp NÉN, nên psql nhận nguyên byte gzip và báo
    "invalid byte sequence for encoding UTF8: 0x8b".
    """
    proc = subprocess.Popen(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            args.database,
            "-c",
            statement,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    total = 0
    assert proc.stdin is not None
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            proc.stdin.write(chunk)
            total += chunk.count(b"\n")
    proc.stdin.close()
    _, err = proc.communicate()
    if proc.returncode:
        print(err.decode("utf-8", "replace").strip(), file=sys.stderr)
        raise SystemExit(1)
    return total


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        print(f"Không thấy {args.db}", file=sys.stderr)
        return 1

    before = int(sql(args, "SELECT count(*) FROM transaction WHERE source_dataset='IBM AML HI-Medium'"))
    print(f"giao dịch IBM đang có: {before:,}")

    tmp = Path(tempfile.mkdtemp(prefix="hi-medium-backfill-"))
    accounts_csv, tx_csv = tmp / "accounts.csv.gz", tmp / "transactions.csv.gz"

    duck = duckdb.connect(str(args.db), read_only=True)
    duck.execute(f"SET threads={args.threads}; SET memory_limit='{args.memory_limit}';")
    print(f"[1/3] Trích phần trước {args.to_date} …", flush=True)
    duck.execute(f"""
        COPY (
          WITH scoped AS (SELECT * FROM "transaction" WHERE occurred_at < DATE '{args.to_date}'),
          keys AS (
            SELECT DISTINCT from_account_key AS account_key FROM scoped
            UNION SELECT DISTINCT to_account_key FROM scoped
          )
          SELECT account_key, 'CUS-' || md5(account_key), split_part(account_key, ':', 1),
                 split_part(account_key, ':', 2), DATE '2022-09-01'
            FROM keys
        ) TO '{accounts_csv.as_posix()}' (FORMAT CSV, HEADER false, COMPRESSION GZIP)
    """)
    duck.execute(f"""
        COPY (
          -- Giữ nguyên đơn vị gốc, không quy đổi USD — cùng quy ước với bộ nạp cũ.
          SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                 amount_paid_orig, payment_currency, amount_received_orig,
                 receiving_currency, channel
            FROM "transaction" WHERE occurred_at < DATE '{args.to_date}'
        ) TO '{tx_csv.as_posix()}' (FORMAT CSV, HEADER false, COMPRESSION GZIP)
    """)
    banks = [
        r[0]
        for r in duck.execute(f"""
        SELECT DISTINCT split_part(k, ':', 1) FROM (
          SELECT from_account_key k FROM "transaction" WHERE occurred_at < DATE '{args.to_date}'
          UNION SELECT to_account_key FROM "transaction" WHERE occurred_at < DATE '{args.to_date}')
    """).fetchall()
    ]
    duck.close()
    print(f"      {len(banks):,} ngân hàng liên quan", flush=True)

    print("[2/3] Nạp ngân hàng, khách hàng, tài khoản …", flush=True)
    # Hơn ba vạn mã ngân hàng: nhét hết vào một câu VALUES thì dòng lệnh vượt
    # giới hạn của execve. Đi qua bảng tạm như hai bảng còn lại.
    banks_csv = tmp / "banks.csv.gz"
    with gzip.open(banks_csv, "wt", encoding="utf-8") as fh:
        for b in banks:
            fh.write(f"{b},Bank {b},unknown\n")
    sql(
        args,
        """DROP TABLE IF EXISTS stage_bank;
                 CREATE TABLE stage_bank (bank_code text, bank_name text, country_source text)""",
    )
    copy_gzip(args, "COPY stage_bank FROM STDIN WITH (FORMAT CSV)", banks_csv)
    sql(
        args,
        """INSERT INTO bank (bank_code, bank_name, country_source)
                 SELECT DISTINCT bank_code, bank_name, country_source FROM stage_bank
                 ON CONFLICT (bank_code) DO NOTHING""",
    )
    sql(args, "DROP TABLE IF EXISTS stage_bank")
    banks_csv.unlink(missing_ok=True)

    sql(
        args,
        """DROP TABLE IF EXISTS stage_account;
                 CREATE TABLE stage_account (account_key text, customer_id text,
                     bank_code text, account_number text, opened_at date)""",
    )
    copy_gzip(args, "COPY stage_account FROM STDIN WITH (FORMAT CSV)", accounts_csv)
    sql(
        args,
        """INSERT INTO customer (customer_id, customer_type, prototype, occupation,
                     declared_income_band, expected_monthly_volume, registered_country,
                     onboarding_date, risk_rating)
                 SELECT DISTINCT customer_id, 'organisation', 'enterprise',
                     'KYC unavailable - IBM AML HI-Medium', 'kyc_unavailable', 0, 'XX',
                     opened_at, 'medium'
                   FROM stage_account ON CONFLICT (customer_id) DO NOTHING""",
    )
    sql(
        args,
        """INSERT INTO account (account_key, customer_id, bank_code, account_number,
                     opened_at, status, dataset)
                 SELECT account_key, customer_id, bank_code, account_number, opened_at,
                        'active', 'ibm_hi_medium'
                   FROM stage_account ON CONFLICT (account_key) DO NOTHING""",
    )

    print("[3/3] Nạp giao dịch …", flush=True)
    sql(
        args,
        """DROP TABLE IF EXISTS stage_tx;
                 CREATE TABLE stage_tx (source_transaction_id text, occurred_at timestamptz,
                     from_account_key text, to_account_key text, amount numeric,
                     currency text, amount_received numeric, receiving_currency text,
                     channel text)""",
    )
    copy_gzip(args, "COPY stage_tx FROM STDIN WITH (FORMAT CSV)", tx_csv)
    sql(
        args,
        f"""INSERT INTO transaction (source_transaction_id, occurred_at, from_account_key,
                      to_account_key, amount, currency, amount_received, receiving_currency,
                      channel, dataset_split, source_dataset, source_file, ingested_at)
                  SELECT source_transaction_id, occurred_at, from_account_key, to_account_key,
                         amount, currency, amount_received, receiving_currency, channel,
                         CASE WHEN occurred_at < TIMESTAMPTZ '{TRAIN_END}' THEN 'train'
                              ELSE 'validation' END,
                         'IBM AML HI-Medium', 'HI-Medium_Trans.csv', now()
                    FROM stage_tx ON CONFLICT DO NOTHING""",
    )
    sql(args, "DROP TABLE IF EXISTS stage_tx; DROP TABLE IF EXISTS stage_account")

    after = int(sql(args, "SELECT count(*) FROM transaction WHERE source_dataset='IBM AML HI-Medium'"))
    span = sql(
        args,
        """SELECT min(occurred_at)::date || ' → ' || max(occurred_at)::date
                          FROM transaction WHERE source_dataset='IBM AML HI-Medium'""",
    )
    print(f"\ngiao dịch IBM: {before:,} → {after:,}  (+{after - before:,})")
    print(f"khoảng thời gian: {span}")
    for path in (accounts_csv, tx_csv):
        path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
