#!/usr/bin/env python3
"""Chuyển điểm MEGA-PNA thành một bản phát hành nạp được vào PostgreSQL.

    python scripts/build_mega_pna_release.py \\
        --predictions models/mega-pna/Small_LI/paper/seed_42_test.parquet \\
        --report      reports/mega-pna/Small_LI/paper/seed_42.json

Vì sao cần script này
---------------------
``scripts/train_mega_pna.py`` xuất điểm theo ``source_edge_id`` — chỉ số dòng
trong file CSV gốc của IBM. ``scripts/load_edge_scores.py`` lại nạp theo
``source_transaction_id`` — mã băm 32 ký tự mà PostgreSQL dùng. Hai đầu không nói
chuyện được với nhau; đây là cái cầu.

Cầu bắc thế nào
---------------
Con đường hiển nhiên — dựng lại chính công thức md5 trong
``scripts/load_ibm_dataset_duckdb.py`` — **không dùng được**, và điều đó đã được
kiểm chứ không phải phỏng đoán. Công thức ấy băm cả ``row_ord``, mà ``row_ord``
sinh bằng ``row_number() OVER ()`` không có ``ORDER BY``. Script nạp ấy không đặt
``preserve_insertion_order``, nên DuckDB đọc CSV song song và đánh số theo thứ tự
luồng nào đọc xong trước. Dựng lại trên cùng máy, cùng file, cùng biểu thức cho ra
**0 dòng khớp** trên 6,1 triệu.

Vậy nên cầu bắc bằng **khoá tự nhiên** thay vì mã băm:

    source_edge_id  →  dòng thứ N của LI-Small_Trans.csv
                    →  (thời điểm, tài khoản gửi, tài khoản nhận,
                        số tiền gửi, tiền tệ gửi,
                        số tiền nhận, tiền tệ nhận)
                    →  transaction_id trong DuckDB
                    →  source_transaction_id trong PostgreSQL

Cả hai mắt xích đều đã đo trên dữ liệu thật:

* ``EdgeID`` của file đã chuyển đổi **bằng đúng** số thứ tự dòng của file gốc —
  6.924.049 dòng đối chiếu, **0 lệch**. Chỗ này tin được vì
  ``format_kaggle_file`` có đặt ``preserve_insertion_order=true``.
* Khoá tự nhiên bảy cột nối được **toàn bộ** 6.119.572 dòng của bảng
  ``transaction``. Chỉ 14 dòng (7 cặp) có khoá trùng nhau; chúng được khử trùng
  bên dưới.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RAW = ROOT / "data/raw/ibm-aml/LI-Small_Trans.csv"
DEFAULT_DB = ROOT / "data/processed/aml.duckdb"

MODEL_VERSION = "fin07_mega_pna_edge_v1"

#: Ngưỡng cảnh báo **phải** là ngưỡng chọn trên tập validation, không phải ngưỡng
#: tối ưu trên test. ``train_one_seed`` đã tính sẵn và cất ở đây.
THRESHOLD_KEY = "test_validation_threshold"

#: Dựng cầu: mỗi dòng file gốc kèm số thứ tự và khoá tự nhiên.
#:
#: ``preserve_insertion_order=true`` là bắt buộc — không có nó thì ``row_number()``
#: đánh số theo thứ tự luồng đọc xong, và cầu nối sai toàn bộ mà không báo lỗi gì.
_BRIDGE_SQL = """
CREATE OR REPLACE TEMP TABLE bridge AS
WITH raw AS (
    SELECT row_number() OVER () - 1 AS edge_id,
           strptime("Timestamp", '%Y/%m/%d %H:%M') AT TIME ZONE 'UTC' AS occurred_at,
           "From Bank" AS from_bank_raw,
           CAST("Account" AS VARCHAR) AS from_account_raw,
           "To Bank" AS to_bank_raw,
           CAST("Account_1" AS VARCHAR) AS to_account_raw,
           CAST("Amount Paid" AS DOUBLE) AS amount_paid_orig,
           CAST("Payment Currency" AS VARCHAR) AS payment_currency,
           CAST("Amount Received" AS DOUBLE) AS amount_received_orig,
           CAST("Receiving Currency" AS VARCHAR) AS receiving_currency
      FROM read_csv_auto(?, header=true, types={'Timestamp': 'VARCHAR'})
)
SELECT edge_id, occurred_at, amount_paid_orig, payment_currency,
       amount_received_orig, receiving_currency,
       -- Chuẩn hoá số hiệu ngân hàng y hệt load_ibm_dataset_duckdb.py: bỏ số 0
       -- ở đầu khi nó là số, giữ nguyên khi không phải.
       CASE WHEN regexp_full_match(trim(CAST(from_bank_raw AS VARCHAR)), '\\d+')
            THEN CAST(CAST(trim(CAST(from_bank_raw AS VARCHAR)) AS BIGINT) AS VARCHAR)
            ELSE trim(CAST(from_bank_raw AS VARCHAR)) END
           || ':' || from_account_raw AS from_account_key,
       CASE WHEN regexp_full_match(trim(CAST(to_bank_raw AS VARCHAR)), '\\d+')
            THEN CAST(CAST(trim(CAST(to_bank_raw AS VARCHAR)) AS BIGINT) AS VARCHAR)
            ELSE trim(CAST(to_bank_raw AS VARCHAR)) END
           || ':' || to_account_raw AS to_account_key
  FROM raw
"""

#: Nối điểm với ``transaction_id``.
#:
#: ``QUALIFY`` khử 7 cặp giao dịch có khoá tự nhiên trùng nhau — hai dòng giống
#: hệt nhau ở cả bảy cột. Không khử thì phép nối nở ra và một ``transaction_id``
#: nhận hai điểm khác nhau, vi phạm khoá chính của ``transaction_model_score``.
_JOIN_SQL = """
SELECT t.transaction_id,
       p.score,
       ? AS threshold,
       p.score >= ? AS triggered,
       CAST(p.is_laundering AS INTEGER) AS target_laundering,
       ? AS model_version
  FROM read_parquet(?) p
  JOIN bridge b ON b.edge_id = p.source_edge_id
  JOIN "transaction" t
    ON t.occurred_at            = b.occurred_at
   AND t.from_account_key       = b.from_account_key
   AND t.to_account_key         = b.to_account_key
   AND t.amount_paid_orig       = b.amount_paid_orig
   AND t.payment_currency       = b.payment_currency
   AND t.amount_received_orig   = b.amount_received_orig
   AND t.receiving_currency     = b.receiving_currency
QUALIFY row_number() OVER (PARTITION BY t.transaction_id ORDER BY p.source_edge_id) = 1
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", type=Path, required=True, help="seed_N_test.parquet")
    parser.add_argument("--report", type=Path, required=True, help="reports/mega-pna/<bộ>/<nhánh>/seed_N.json")
    parser.add_argument("--benchmark", type=Path, help="reports/mega-pna/benchmark.json, để lấy số trung bình 5 seed")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    # Mặc định suy ra từ bộ dữ liệu ghi trong báo cáo, không cố định vào Small_LI:
    # chạy Small_HI mà ghi đè lên file của Small_LI là lỗi im lặng.
    parser.add_argument("--scores-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--memory-limit", default="12GB")
    return parser.parse_args(argv)


def _over_seeds(benchmark: Path | None, dataset: str, arm: str) -> dict[str, Any] | None:
    """Lấy trung bình ± độ lệch 5 seed, nếu cổng nghiệm thu đã chạy xong."""
    if benchmark is None or not benchmark.is_file():
        return None
    payload = json.loads(benchmark.read_text(encoding="utf-8"))
    for row in payload.get("datasets", []):
        if row.get("dataset") == dataset and row.get("arm") == arm and row.get("aggregate"):
            return {
                "f1": row["aggregate"]["f1"],
                "precision": row["aggregate"]["precision"],
                "recall": row["aggregate"]["recall"],
                "pr_auc": row["aggregate"]["pr_auc"],
                "seeds": [entry["seed"] for entry in row.get("runs", [])],
                "published_reference": row.get("published_reference"),
                "within_published_one_std": row.get("within_published_one_std"),
            }
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for path in (args.predictions, args.report, args.raw, args.db):
        if not path.is_file():
            raise FileNotFoundError(path)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    dataset = report.get("dataset", "Small_LI")
    arm = report.get("arm", "paper")
    if args.scores_out is None:
        args.scores_out = ROOT / f"data/processed/mega-pna/{dataset}/pg_scores.parquet"
    if args.report_out is None:
        args.report_out = ROOT / f"reports/mega-pna/{dataset}/release.json"

    if THRESHOLD_KEY not in report:
        raise KeyError(
            f"{args.report} thiếu khoá {THRESHOLD_KEY!r}. Ngưỡng bắt buộc phải là "
            "ngưỡng chọn trên validation; đừng tự chọn ngưỡng trên test."
        )
    threshold = float(report[THRESHOLD_KEY]["threshold"])
    print(f"[1/4] Ngưỡng chọn trên validation: {threshold:.6f}", flush=True)

    args.scores_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        con.execute("SET TimeZone='UTC'")
        # Bắt buộc: xem chú thích ở _BRIDGE_SQL.
        con.execute("SET preserve_insertion_order=true")
        con.execute(f"SET threads={int(args.threads)}")
        con.execute(f"SET memory_limit='{args.memory_limit}'")

        print("[2/4] Dựng cầu nối từ file gốc ...", flush=True)
        con.execute(_BRIDGE_SQL, [str(args.raw)])
        bridge_rows = con.execute("SELECT count(*) FROM bridge").fetchone()[0]

        scored = con.execute("SELECT count(*) FROM read_parquet(?)", [str(args.predictions)]).fetchone()[0]

        print("[3/4] Nối điểm với transaction_id ...", flush=True)
        con.execute(
            f"COPY ({_JOIN_SQL}) TO '{args.scores_out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)",
            [threshold, threshold, MODEL_VERSION, str(args.predictions)],
        )
        linked, triggered, positives = con.execute(
            """SELECT count(*), count(*) FILTER (WHERE triggered),
                      count(*) FILTER (WHERE target_laundering = 1)
                 FROM read_parquet(?)""",
            [str(args.scores_out)],
        ).fetchone()

        # Số dòng rơi ra PHẢI gần bằng số giao dịch tự chuyển trong tập test —
        # PostgreSQL không có chúng. Rơi ra 0 nghĩa là cầu nối sai, rơi ra quá
        # nhiều cũng vậy.
        self_loops = con.execute(
            """SELECT count(*) FROM read_parquet(?) p JOIN bridge b ON b.edge_id = p.source_edge_id
                WHERE b.from_account_key = b.to_account_key""",
            [str(args.predictions)],
        ).fetchone()[0]
    finally:
        con.close()

    dropped = scored - linked
    unexplained = dropped - self_loops

    print(f"[4/4] Cầu nối     : {bridge_rows:,} dòng file gốc", flush=True)
    print(f"      Điểm vào    : {scored:,}", flush=True)
    print(f"      Nối được    : {linked:,}", flush=True)
    print(
        f"      Rơi ra      : {dropped:,}  (tự chuyển {self_loops:,}, không giải thích được {unexplained:,})",
        flush=True,
    )
    print(f"      Vượt ngưỡng : {triggered:,}", flush=True)
    print(f"      Nhãn dương  : {positives:,}", flush=True)

    if linked == 0:
        raise SystemExit("Nối được 0 dòng — cầu nối sai. Dừng lại, đừng nạp.")
    if unexplained:
        raise SystemExit(
            f"{unexplained:,} dòng rơi ra mà không phải giao dịch tự chuyển. Cầu nối chưa đúng; kiểm lại trước khi nạp."
        )

    release = {
        "schema_version": "fin07.mega_pna.release.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": dataset,
        "arm": arm,
        "model_version": MODEL_VERSION,
        "seed": report.get("seed"),
        "best_epoch": report.get("best_epoch"),
        "config": report.get("config"),
        "split": report.get("split"),
        # load_edge_scores.py lấy len(report["features"]) làm feature_count.
        "features": list(report.get("feature_names", [])),
        "policy": {
            "threshold": threshold,
            "threshold_source": "validation split, best-F1",
            "join": "source_edge_id → dòng CSV gốc → khoá tự nhiên 7 cột → transaction_id",
            "scored_rows": scored,
            "linked_rows": linked,
            "dropped_self_transfers": self_loops,
        },
        "test_primary_seed": report.get("test_paper_protocol"),
        "test_over_seeds": _over_seeds(args.benchmark, dataset, arm),
        "operating_points": report.get("operational_budget"),
    }
    args.report_out.write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nĐã ghi {args.scores_out}")
    print(f"Đã ghi {args.report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
