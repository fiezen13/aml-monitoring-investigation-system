#!/usr/bin/env python3
"""Tính điểm nhánh Rule trên đúng lưới (tài khoản, mốc thời gian) của fusion.

Hộp 5 trong sơ đồ kiến trúc hợp nhất ba nhánh, nhưng bản fusion hiện có chỉ nhận
hai: Isolation Forest và Graph. Thiếu mảnh thứ ba vì **chưa từng có điểm rule ở
dạng lưới** — nhánh rule chỉ chạy trực tiếp trên PostgreSQL cho một mốc.

Script này lấp đúng mảnh đó: với mỗi mốc trong
``data/processed/fusion-v2/fusion_scores.parquet``, nó gom số liệu 7 ngày trong
DuckDB rồi chạy chính bộ luật ở ``src/detection/rules.py`` — cùng một bộ luật mà
đường chạy trực tuyến dùng, không viết lại lần hai.

Đầu ra: parquet ``(account_key, as_of_ts, rule_score, rule_hits)``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.detection.rules import RULE_THRESHOLDS, RuleContext, evaluate, risk_score  # noqa: E402

DEFAULT_DB = ROOT / "data/processed/aml.duckdb"
DEFAULT_GRID = ROOT / "data/processed/fusion-v2/fusion_scores.parquet"
DEFAULT_OUT = ROOT / "data/processed/fusion-v2/rule_scores.parquet"

#: Gom số liệu một cửa sổ [as_of - 7 ngày, as_of) cho mọi tài khoản có phát sinh.
#:
#: Bản sao DuckDB của ``_AGGREGATE_SQL`` trong ``src/detection/rule_engine.py``.
#: Hai bản phải cho cùng kết quả; khác biệt duy nhất là nguồn dữ liệu (DuckDB cho
#: huấn luyện, PostgreSQL cho phục vụ) và ở đây không có bảng ``bank`` nên hai
#: luật cần dữ liệu ngân hàng được xử lý riêng bên dưới.
_AGG_SQL = """
WITH win AS (
    SELECT occurred_at, from_account_key, to_account_key, amount
      FROM "transaction"
     WHERE occurred_at >= ? AND occurred_at < ?
),
sided AS (
    SELECT from_account_key AS account_key, 'out' AS direction, occurred_at, amount FROM win
    UNION ALL
    SELECT to_account_key AS account_key, 'in' AS direction, occurred_at, amount FROM win
),
near AS (
    SELECT account_key, count(*) AS near_count,
           count(DISTINCT round(amount, 2)) AS near_distinct,
           date_diff('second', min(occurred_at), max(occurred_at)) / 3600.0 AS near_span_hours
      FROM sided
     WHERE direction = 'out' AND amount >= ? AND amount < ?
     GROUP BY account_key
),
marked AS (
    SELECT account_key, direction, occurred_at, amount,
           max(CASE WHEN direction = 'in' THEN occurred_at END)
               OVER (PARTITION BY account_key ORDER BY occurred_at
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS last_in
      FROM sided
),
rapid AS (
    SELECT account_key,
           coalesce(sum(CASE WHEN direction = 'out' AND last_in IS NOT NULL
                              AND date_diff('second', last_in, occurred_at) <= 7200
                             THEN amount END), 0) AS rapid_amount,
           median(CASE WHEN direction = 'out' AND last_in IS NOT NULL
                       THEN date_diff('second', last_in, occurred_at) / 3600.0 END) AS dwell
      FROM marked
     GROUP BY account_key
),
agg AS (
    SELECT account_key,
           count(*) FILTER (direction = 'out') AS outgoing_count,
           count(*) FILTER (direction = 'in') AS incoming_count,
           coalesce(sum(amount) FILTER (direction = 'out'), 0) AS total_outflow,
           coalesce(sum(amount) FILTER (direction = 'in'), 0) AS total_inflow,
           count(*) AS transaction_count
      FROM sided GROUP BY account_key
)
SELECT a.account_key, a.outgoing_count, a.incoming_count, a.total_outflow, a.total_inflow,
       a.transaction_count,
       coalesce(n.near_count, 0) AS near_count,
       coalesce(n.near_distinct, 0) AS near_distinct,
       coalesce(n.near_span_hours, 0) AS near_span_hours,
       coalesce(r.rapid_amount, 0) AS rapid_amount,
       r.dwell AS dwell
  FROM agg a
  LEFT JOIN near n USING (account_key)
  LEFT JOIN rapid r USING (account_key)
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="12GB")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(args.db), read_only=True)
    con.execute(f"SET threads={args.threads}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")

    snapshots = [
        row[0]
        for row in duckdb.connect()
        .execute("SELECT DISTINCT as_of_ts FROM read_parquet(?) ORDER BY 1", [str(args.grid)])
        .fetchall()
    ]
    print(f"[1/2] {len(snapshots)} mốc thời gian cần tính", flush=True)

    threshold = RULE_THRESHOLDS["reporting_threshold"]
    band_floor = threshold * RULE_THRESHOLDS["structuring_band_floor"]

    writer: pq.ParquetWriter | None = None
    total = 0
    try:
        for index, as_of in enumerate(snapshots, start=1):
            window_start = as_of - timedelta(days=args.window_days)
            rows = con.execute(_AGG_SQL, [window_start, as_of, band_floor, threshold]).fetchall()

            keys: list[str] = []
            scores: list[float] = []
            hits_count: list[int] = []
            for r in rows:
                ctx = RuleContext(
                    account_key=r[0],
                    as_of=as_of,
                    window_days=args.window_days,
                    outgoing_count=int(r[1]),
                    incoming_count=int(r[2]),
                    total_outflow=float(r[3]),
                    total_inflow=float(r[4]),
                    transaction_count=int(r[5]),
                    near_threshold_count=int(r[6]),
                    near_threshold_distinct_amounts=int(r[7]),
                    near_threshold_span_hours=float(r[8]),
                    rapid_outflow_amount=float(r[9]),
                    median_dwell_hours=float(r[10]) if r[10] is not None else None,
                    # Hai luật cần dữ liệu ngân hàng (VASP, xuyên biên giới) không
                    # chạy ở đây: DuckDB huấn luyện không có bảng `bank`. Chúng chỉ
                    # làm giàu ngữ cảnh, không đổi việc một tài khoản có bị cảnh báo
                    # hay không — xem `should_alert`.
                )
                hits = evaluate(ctx)
                if not hits:
                    continue
                keys.append(r[0])
                scores.append(risk_score(hits) / 100.0)
                hits_count.append(len(hits))

            table = pa.table(
                {
                    "account_key": pa.array(keys, pa.string()),
                    "as_of_ts": pa.array([as_of] * len(keys), pa.timestamp("us", tz="UTC")),
                    "rule_score": pa.array(scores, pa.float64()),
                    "rule_hits": pa.array(hits_count, pa.int32()),
                }
            )
            if writer is None:
                writer = pq.ParquetWriter(args.output, table.schema, compression="zstd")
            writer.write_table(table)
            total += len(keys)
            print(
                f"      [{index}/{len(snapshots)}] {as_of:%Y-%m-%d}  {len(keys):>7,} tài khoản có luật kích hoạt",
                flush=True,
            )
    finally:
        if writer is not None:
            writer.close()
        con.close()

    print(f"[2/2] Xong: {total:,} dòng -> {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
