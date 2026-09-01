#!/usr/bin/env python3
"""Nạp SAML-D vào lược đồ dùng chung, làm nền cho nhánh luật địa lý.

    python scripts/load_saml_d.py --csv SAML-D.csv
    python scripts/load_saml_d.py --csv SAML-D.csv --limit 200000   # chạy thử

Vì sao nạp vào chính bảng `transaction` và `account`
---------------------------------------------------
Bộ công cụ của tác tử đọc thẳng hai bảng ấy. Nạp vào bảng riêng thì phải viết
lại `GetTransactions`, `GetAccountBehavior` và mọi truy vấn phía sau — tức là
nhân đôi tầng phục vụ cho một nhánh dữ liệu. Dùng chung bảng, tách bằng cột
``dataset``, thì tác tử chạy trên SAML-D mà không sửa một dòng nào.

Khoá tài khoản
--------------
SAML-D không có mã ngân hàng, chỉ có vị trí ngân hàng của bên gửi và bên nhận
trên từng giao dịch. Ràng buộc ``account_key_format`` đòi khoá phải là
``mã_ngân_hàng:số_tài_khoản``, nên vị trí đóng vai mã ngân hàng, viết bằng mã
ISO hai chữ: ``GB:8724731955``.

6.507 trên 855.460 tài khoản (0,76%) xuất hiện ở nhiều hơn một quốc gia. Lấy
quốc gia XUẤT HIỆN NHIỀU NHẤT, hoà thì lấy theo thứ tự bảng chữ cái — cốt để
hai lần chạy cho ra cùng một khoá. Chọn bừa thì khoá đổi giữa các lần nạp và
mọi cảnh báo cũ trỏ vào hư không.

KYC
---
SAML-D không có dữ liệu khách hàng. Theo đúng cách nhánh IBM đã làm, mỗi tài
khoản có một bản ghi khách hàng đánh dấu rõ là không có KYC, thay vì bịa nghề
nghiệp và thu nhập. Riêng ``registered_country`` là dữ liệu THẬT — vị trí ngân
hàng do chính bộ dữ liệu cung cấp.

Chia dữ liệu
------------
Cắt theo ranh giới ngày 60/20/20 trên 321 ngày. Nhánh này dùng luật nên không
huấn luyện, nhưng ngưỡng vẫn phải chốt trên validation và báo cáo trên test —
cùng một giao thức với nhánh MEGA-PNA, để hai nhánh so được với nhau.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

DATASET = "saml_d"
SOURCE_DATASET = "SAML-D"

# Vị trí ngân hàng trong SAML-D viết bằng tên thường; cột `registered_country`
# là CHAR(2) nên phải quy về ISO 3166-1 alpha-2.
ISO2 = {
    "UK": "GB",
    "USA": "US",
    "UAE": "AE",
    "Turkey": "TR",
    "Switzerland": "CH",
    "Pakistan": "PK",
    "Nigeria": "NG",
    "Spain": "ES",
    "Germany": "DE",
    "Italy": "IT",
    "France": "FR",
    "Japan": "JP",
    "Morocco": "MA",
    "Austria": "AT",
    "Mexico": "MX",
    "Albania": "AL",
    "India": "IN",
    "Netherlands": "NL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "SAML-D.csv")
    parser.add_argument("--limit", type=int, default=0, help="0 = nạp toàn bộ")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/saml-d-load"))
    parser.add_argument("--container", default="fin07-postgres-1")
    parser.add_argument("--database", default="fin07_hi_medium")
    parser.add_argument("--db-user", default="fin07")
    return parser.parse_args()


def iso2_case(column: str) -> str:
    """Biểu thức CASE ánh xạ tên quốc gia sang mã ISO ngay trong SQL."""
    arms = " ".join(f"WHEN '{name}' THEN '{code}'" for name, code in ISO2.items())
    # Quốc gia lạ thì để 'XX' chứ không đoán — và bước kiểm tra bên dưới sẽ báo.
    return f"CASE {column} {arms} ELSE 'XX' END"


def psql(args: argparse.Namespace, sql: str) -> str:
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
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def copy_csv(args: argparse.Namespace, table: str, columns: str, path: Path) -> None:
    with path.open("rb") as handle:
        subprocess.run(
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
                f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)",
            ],
            stdin=handle,
            check=True,
            capture_output=True,
            text=False,
        )


def main() -> int:
    args = parse_args()
    if not args.csv.exists():
        print(f"Không thấy {args.csv}", file=sys.stderr)
        return 1
    args.work_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=true; SET threads=6;")
    limit = f"LIMIT {args.limit}" if args.limit else ""
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT *, row_number() OVER () AS line_no
        FROM read_csv_auto('{args.csv.as_posix()}') {limit}
    """)
    rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    print(f"đã đọc {rows:,} giao dịch")

    # --- Quốc gia của mỗi tài khoản: chọn theo tần suất, hoà thì theo bảng chữ cái ---
    con.execute(f"""
        CREATE TABLE acct AS
        WITH seen AS (
            SELECT CAST(Sender_account AS VARCHAR) acc, Sender_bank_location loc FROM raw
            UNION ALL
            SELECT CAST(Receiver_account AS VARCHAR), Receiver_bank_location FROM raw
        ), tally AS (
            SELECT acc, loc, count(*) n FROM seen GROUP BY 1, 2
        ), ranked AS (
            SELECT acc, loc, row_number() OVER (PARTITION BY acc ORDER BY n DESC, loc ASC) rn
            FROM tally
        )
        SELECT acc AS account_number, loc AS location,
               {iso2_case("loc")} AS bank_code,
               {iso2_case("loc")} || ':' || acc AS account_key
        FROM ranked WHERE rn = 1
    """)
    n_acct = con.execute("SELECT count(*) FROM acct").fetchone()[0]
    unknown = con.execute("SELECT count(*) FROM acct WHERE bank_code = 'XX'").fetchone()[0]
    print(f"đã dựng {n_acct:,} tài khoản" + (f" · {unknown:,} quốc gia chưa có mã ISO" if unknown else ""))
    if unknown:
        print("  → bổ sung vào bảng ISO2 rồi chạy lại; không nạp khi còn quốc gia lạ", file=sys.stderr)
        return 2

    # --- Chia theo ranh giới ngày 60/20/20 ---
    bounds = con.execute("""
        WITH d AS (SELECT DISTINCT CAST(Date AS DATE) AS d_day FROM raw),
             n AS (SELECT count(*) AS c FROM d),
             r AS (SELECT d_day, row_number() OVER (ORDER BY d_day) AS rn FROM d)
        SELECT (SELECT min(d_day) FROM r WHERE rn > (SELECT c FROM n) * 0.6),
               (SELECT min(d_day) FROM r WHERE rn > (SELECT c FROM n) * 0.8)
    """).fetchone()
    val_start, test_start = bounds
    print(f"chia dữ liệu: validation từ {val_start}, test từ {test_start}")

    # --- Xuất khách hàng và tài khoản ---
    cus = args.work_dir / "customer.csv"
    con.execute(f"""COPY (
        SELECT 'CUS-SAMLD-' || account_key AS customer_id,
               'organisation' AS customer_type, 'enterprise' AS prototype,
               'KYC unavailable - SAML-D' AS occupation,
               'kyc_unavailable' AS declared_income_band,
               0 AS expected_monthly_volume,
               bank_code AS registered_country,
               DATE '2022-10-07' AS onboarding_date,
               'medium' AS risk_rating
        FROM acct) TO '{cus.as_posix()}' (FORMAT csv, HEADER true)""")

    acc = args.work_dir / "account.csv"
    con.execute(f"""COPY (
        SELECT account_key, 'CUS-SAMLD-' || account_key AS customer_id,
               bank_code, account_number,
               DATE '2022-10-07' AS opened_at, 'active' AS status,
               '{DATASET}' AS dataset
        FROM acct) TO '{acc.as_posix()}' (FORMAT csv, HEADER true)""")

    # --- Xuất giao dịch ---
    txn = args.work_dir / "transaction.csv"
    con.execute(f"""COPY (
        SELECT
            CAST(r.Date AS VARCHAR) || ' ' || r.Time || '+00' AS occurred_at,
            s.account_key AS from_account_key,
            t.account_key AS to_account_key,
            r.Amount AS amount,
            r.Payment_currency AS currency,
            r.Amount AS amount_received,
            r.Received_currency AS receiving_currency,
            r.Payment_type AS channel,
            CASE WHEN CAST(r.Date AS DATE) >= DATE '{test_start}' THEN 'test'
                 WHEN CAST(r.Date AS DATE) >= DATE '{val_start}'  THEN 'validation'
                 ELSE 'train' END AS dataset_split,
            CAST(r.line_no AS VARCHAR) AS source_transaction_id,
            '{SOURCE_DATASET}' AS source_dataset,
            r.line_no AS source_line_number,
            r.Sender_bank_location AS from_country,
            r.Receiver_bank_location AS to_country
        FROM raw r
        JOIN acct s ON s.account_number = CAST(r.Sender_account AS VARCHAR)
        JOIN acct t ON t.account_number = CAST(r.Receiver_account AS VARCHAR)
        ORDER BY r.line_no) TO '{txn.as_posix()}' (FORMAT csv, HEADER true)""")

    # Nhãn đối chứng để chấm điểm bộ luật. KHÔNG nạp vào `transaction`: nó là
    # ĐÁP ÁN. Notebook gốc để `Laundering_type` trong đặc trưng đầu vào và ra
    # AUC 1.0 — đúng dấu hiệu mô hình đọc được đáp án.
    lbl = args.work_dir / "label.csv"
    con.execute(f"""COPY (
        SELECT line_no AS source_line_number, Is_laundering AS is_laundering,
               Laundering_type AS laundering_type
        FROM raw ORDER BY line_no) TO '{lbl.as_posix()}' (FORMAT csv, HEADER true)""")
    print("đã xuất 4 tệp trung gian")

    # --- Nạp ---
    psql(args, "CREATE SCHEMA IF NOT EXISTS label")
    psql(
        args,
        """CREATE TABLE IF NOT EXISTS label.saml_d_truth (
        source_line_number BIGINT PRIMARY KEY,
        is_laundering SMALLINT NOT NULL,
        laundering_type TEXT NOT NULL)""",
    )
    psql(args, f"DELETE FROM alert WHERE dataset = '{DATASET}'")
    psql(args, f"DELETE FROM transaction WHERE source_dataset = '{SOURCE_DATASET}'")
    psql(args, f"DELETE FROM account WHERE dataset = '{DATASET}'")
    psql(args, "DELETE FROM customer WHERE customer_id LIKE 'CUS-SAMLD-%'")
    psql(args, "TRUNCATE label.saml_d_truth")

    print("nạp khách hàng…")
    copy_csv(
        args,
        "customer",
        "customer_id,customer_type,prototype,occupation,declared_income_band,"
        "expected_monthly_volume,registered_country,onboarding_date,risk_rating",
        cus,
    )
    print("nạp tài khoản…")
    copy_csv(args, "account", "account_key,customer_id,bank_code,account_number,opened_at,status,dataset", acc)
    print("nạp giao dịch…")
    copy_csv(
        args,
        "transaction",
        "occurred_at,from_account_key,to_account_key,amount,currency,amount_received,"
        "receiving_currency,channel,dataset_split,source_transaction_id,source_dataset,"
        "source_line_number,from_country,to_country",
        txn,
    )
    print("nạp nhãn đối chứng…")
    copy_csv(args, "label.saml_d_truth", "source_line_number,is_laundering,laundering_type", lbl)

    # --- Đối chiếu ---
    got_txn = int(psql(args, f"SELECT count(*) FROM transaction WHERE source_dataset='{SOURCE_DATASET}'"))
    got_acc = int(psql(args, f"SELECT count(*) FROM account WHERE dataset='{DATASET}'"))
    got_lbl = int(psql(args, "SELECT count(*) FROM label.saml_d_truth"))
    print(f"\ngiao dịch  {got_txn:,} / {rows:,}")
    print(f"tài khoản  {got_acc:,} / {n_acct:,}")
    print(f"nhãn       {got_lbl:,} / {rows:,}")
    if got_txn != rows or got_acc != n_acct or got_lbl != rows:
        print("SỐ DÒNG KHÔNG KHỚP", file=sys.stderr)
        return 3
    print("khớp toàn bộ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
