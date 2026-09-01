#!/usr/bin/env python3
"""Gom điểm cạnh MEGA-PNA về mức TÀI KHOẢN — đơn vị của bảng ``alert``.

    python scripts/aggregate_mega_pna_accounts.py --split validation
    python scripts/aggregate_mega_pna_accounts.py --split test

Vì sao cần
----------
MEGA-PNA chấm **giao dịch**. Bảng ``alert`` khoá theo ``account_key``, và toàn bộ
hàng đợi, phiên điều tra, hồ sơ vụ việc đều xoay quanh tài khoản. Không có bước
này thì điểm mô hình không nối được vào tầng phục vụ.

Bốn số đo, không phải một
-------------------------
Một cạnh 0,99 lẻ loi **khác** mười cạnh 0,75 liên tiếp: cái đầu có thể là nhiễu,
cái sau là khuôn mẫu. Nên mỗi ô mang bốn số đo, và chính chúng đi vào chứng cứ
cho tác tử: *"12 giao dịch vượt ngưỡng, tổng 240.000 USD, cạnh cao nhất 0,97"*.

Định nghĩa ô và nhãn
--------------------
Ô là ``(account_key, as_of)`` với ``as_of`` là cuối mỗi ngày tài khoản **có phát
sinh**. Không dựng ô cho ngày im lặng: chúng không sinh cảnh báo, mà lại làm lưới
phình lên nhiều lần.

Cửa sổ nhìn lại 7 ngày, tính **cả hai chiều** gửi và nhận — tài khoản trung
chuyển chỉ lộ ra khi nhìn cả tiền vào lẫn tiền ra.

Nhãn của ô là 1 nếu **bất kỳ** giao dịch nào của tài khoản trong cửa sổ mang nhãn
rửa tiền. Đây là định nghĩa chuẩn ở mức tài khoản, và nó khớp với cách bộ nhãn
IBM gán theo cụm chứ không theo từng cạnh rời.

Cầu nối
-------
``source_edge_id`` của MEGA-PNA là **số thứ tự dòng file CSV gốc, đếm từ 0** — đã
đối chiếu toàn bộ 6.924.049 dòng của LI-Small, 0 lệch. ``preserve_insertion_order``
là bắt buộc; thiếu nó thì DuckDB đọc song song và số thứ tự sai toàn bộ mà không
báo lỗi gì.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RAW = ROOT / "data/raw/ibm-aml/HI-Medium_Trans.csv"
DEFAULT_SCORES = ROOT / "models/mega-pna/Medium_HI/paper"
DEFAULT_OUT = ROOT / "data/processed/mega-pna-accounts"

#: Ngưỡng đếm "cạnh vượt ngưỡng". Lấy từ ngưỡng chốt trên validation của lần
#: huấn luyện; để tham số hoá vì nó là quyết định vận hành, không phải hằng số.
DEFAULT_EDGE_THRESHOLD = 0.56933

_BRIDGE_SQL = """
CREATE OR REPLACE TEMP TABLE bridge AS
SELECT row_number() OVER () - 1 AS edge_id,
       strptime("Timestamp", '%Y/%m/%d %H:%M') AT TIME ZONE 'UTC' AS occurred_at,
       CASE WHEN regexp_full_match(trim(CAST("From Bank" AS VARCHAR)), '\\d+')
            THEN CAST(CAST(trim(CAST("From Bank" AS VARCHAR)) AS BIGINT) AS VARCHAR)
            ELSE trim(CAST("From Bank" AS VARCHAR)) END || ':' || CAST("Account" AS VARCHAR) AS from_key,
       CASE WHEN regexp_full_match(trim(CAST("To Bank" AS VARCHAR)), '\\d+')
            THEN CAST(CAST(trim(CAST("To Bank" AS VARCHAR)) AS BIGINT) AS VARCHAR)
            ELSE trim(CAST("To Bank" AS VARCHAR)) END || ':' || CAST("Account_1" AS VARCHAR) AS to_key,
       CAST("Amount Paid" AS DOUBLE) AS amount,
       CAST("Payment Currency" AS VARCHAR) AS currency
  FROM read_csv_auto(?, header=true, types={'Timestamp': 'VARCHAR'})
"""

#: Mỗi cạnh xuất hiện hai lần — một lần cho tài khoản gửi, một lần cho tài khoản
#: nhận. Đó là chủ ý: rủi ro của một cạnh thuộc về cả hai đầu.
_SIDED_SQL = """
CREATE OR REPLACE TEMP TABLE sided AS
SELECT b.from_key AS account_key, 'out' AS direction, b.occurred_at, b.amount, b.currency,
       p.score, p.is_laundering
  FROM read_parquet(?) p JOIN bridge b ON b.edge_id = p.source_edge_id
UNION ALL
SELECT b.to_key, 'in', b.occurred_at, b.amount, b.currency, p.score, p.is_laundering
  FROM read_parquet(?) p JOIN bridge b ON b.edge_id = p.source_edge_id
"""

#: Ô và bốn số đo, tính trên cửa sổ 7 ngày kết thúc tại ``as_of``.
#:
#: Dùng nối theo khoảng thay vì hàm cửa sổ: cửa sổ trượt theo THỜI GIAN chứ không
#: theo số dòng, mà hàm cửa sổ của DuckDB đếm theo dòng.
_AGGREGATE_SQL = """
WITH cells AS (
    SELECT account_key, (occurred_at::DATE + INTERVAL 1 DAY) AS as_of
      FROM sided GROUP BY 1, 2
),
joined AS (
    SELECT c.account_key, c.as_of, s.score, s.amount, s.is_laundering, s.direction
      FROM cells c
      JOIN sided s
        ON s.account_key = c.account_key
       AND s.occurred_at < c.as_of
       AND s.occurred_at >= c.as_of - INTERVAL {window} DAY
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY account_key, as_of ORDER BY score DESC) AS rk
      FROM joined
)
SELECT account_key,
       as_of,
       max(score)                                              AS score_max,
       avg(score) FILTER (rk <= 5)                             AS score_top5_mean,
       count(*) FILTER (score >= {threshold})                  AS edges_over_threshold,
       coalesce(sum(amount) FILTER (score >= {threshold}), 0)  AS flagged_amount,
       count(*)                                                AS edge_count,
       count(*) FILTER (direction = 'in')                      AS incoming_count,
       count(*) FILTER (direction = 'out')                     AS outgoing_count,
       max(is_laundering)                                      AS label
  FROM ranked
 GROUP BY 1, 2
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--scores-dir", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--edge-threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--memory-limit", default="16GB")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scores = args.scores_dir / f"seed_42_{args.split}.parquet"
    for path in (args.raw, scores):
        if not path.is_file():
            raise FileNotFoundError(path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{args.split}.parquet"

    con = duckdb.connect()
    try:
        # Bắt buộc: không có nó thì row_number() đánh số theo luồng đọc xong
        # trước, và cầu nối sai toàn bộ mà không báo lỗi gì.
        con.execute("SET preserve_insertion_order=true")
        con.execute("SET TimeZone='UTC'")
        con.execute(f"SET threads={int(args.threads)}")
        con.execute(f"SET memory_limit='{args.memory_limit}'")

        print("[1/3] Dựng cầu nối từ file gốc ...", flush=True)
        con.execute(_BRIDGE_SQL, [str(args.raw)])

        print("[2/3] Trải cạnh về hai đầu tài khoản ...", flush=True)
        con.execute(_SIDED_SQL, [str(scores), str(scores)])
        edges = con.execute("SELECT count(*) FROM sided").fetchone()[0]

        print(f"[3/3] Gom về ô (tài khoản, ngày), cửa sổ {args.window_days} ngày ...", flush=True)
        sql = _AGGREGATE_SQL.format(window=int(args.window_days), threshold=float(args.edge_threshold))
        con.execute(f"COPY ({sql}) TO '{output.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

        cells, positives, accounts = con.execute(
            "SELECT count(*), sum(label), count(DISTINCT account_key) FROM read_parquet(?)",
            [str(output)],
        ).fetchone()
    finally:
        con.close()

    print(
        f"\n{args.split}: {cells:,} ô · {accounts:,} tài khoản · {positives:,} ô dương ({positives / cells * 100:.4f}%)"
    )
    print(f"cạnh đã trải hai đầu: {edges:,}")
    print(f"đã ghi {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
