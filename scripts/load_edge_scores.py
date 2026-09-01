#!/usr/bin/env python3
"""Nạp một bản phát hành mô hình edge vào cơ sở dữ liệu **đang có dữ liệu**.

Khác với ``scripts/load_currency_native_edge_release.py``: script đó là bộ nạp
từ đầu — nó đòi ``(customer, transaction, alert, edge_model_release)`` đều bằng 0
rồi tự nạp giao dịch của riêng nó. Dùng được đúng một lần, lúc dựng cơ sở dữ
liệu từ con số không.

Script này giải quyết trường hợp còn lại: giao dịch **đã nằm sẵn** trong
PostgreSQL (do ``load_fusion_release.py`` nạp), và ta chỉ cần gắn thêm điểm của
mô hình edge để ba trang console sống lại:

* ``/api/v1/transactions`` — tra cứu giao dịch
* ``/api/v1/fc/crypto``    — truy vết tài sản mã hoá
* ``/api/v1/world``        — giám sát địa lý ở chế độ vận hành

Cả ba đều truy vấn qua ``transaction_model_score``; một bản phát hành làm sống
cả ba cùng lúc, không phải sửa truy vấn nào.

Script **không** tạo cảnh báo. Ba nhánh phát hiện (rule / anomaly / graph) đã
sinh cảnh báo riêng; thêm một nguồn nữa sẽ làm nhiễu số liệu theo nhánh mà không
thêm thông tin gì cho ba trang trên.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True, help="Parquet điểm từng giao dịch")
    parser.add_argument("--report", type=Path, required=True, help="JSON benchmark của lần huấn luyện")
    parser.add_argument("--model", type=Path, required=True, help="File .joblib của mô hình")
    parser.add_argument("--db", type=Path, required=True, help="DuckDB nguồn, dùng để lấy checksum")
    parser.add_argument("--dataset", required=True, help="Tên bộ dữ liệu, ví dụ 'IBM AML LI-Small currency-native'")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _psycopg_url(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL phải là PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    for path in (args.scores, args.report, args.model, args.db):
        if not path.is_file():
            raise FileNotFoundError(path)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    con = duckdb.connect()
    try:
        stats = con.execute(
            """SELECT count(*), count(*) FILTER (WHERE triggered),
                      count(*) FILTER (WHERE target_laundering = 1),
                      any_value(threshold), any_value(model_version)
                 FROM read_parquet(?)""",
            [str(args.scores)],
        ).fetchone()
    finally:
        con.close()

    rows, triggered, positives, threshold, model_version = stats
    return {
        "release_id": "REL-EDGE-" + hashlib.sha1(f"{args.dataset}|{sha256_file(args.model)}".encode()).hexdigest()[:16],
        "model_version": str(model_version or "currency_native_policy_edge"),
        "dataset": args.dataset,
        "model_sha256": sha256_file(args.model),
        "scores_sha256": sha256_file(args.scores),
        "source_database_sha256": sha256_file(args.db),
        "threshold": float(threshold),
        "transaction_rows": int(rows),
        "positive_rows": int(positives),
        "triggered_rows": int(triggered),
        # Danh sách đặc trưng nằm ở khoá `features` của báo cáo, không nằm trong
        # `policy`. Lấy sai chỗ cho ra 0 và vi phạm ràng buộc feature_count > 0.
        "feature_count": len(report["features"]),
        "benchmark": {
            "primary_seed": report.get("test_primary_seed"),
            "over_seeds": report.get("test_over_seeds"),
            "operating_points": report.get("operating_points"),
        },
        "policy": report.get("policy", {}),
    }


def load(pg: psycopg.Connection[Any], plan: dict[str, Any], scores: Path) -> dict[str, Any]:
    """Ghi bản phát hành và điểm từng giao dịch, rồi kích hoạt."""
    existing = pg.execute("SELECT status FROM edge_model_release WHERE release_id=%s", (plan["release_id"],)).fetchone()
    if existing and existing[0] == "active":
        return {"status": "already_active", "release_id": plan["release_id"]}

    pg.execute(
        """INSERT INTO edge_model_release (
               release_id, model_version, dataset, split, model_sha256, scores_sha256,
               source_database_sha256, threshold, transaction_rows, positive_rows,
               triggered_rows, feature_count, benchmark, policy, status, trained_at
           ) VALUES (%s,%s,%s,'test',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'loading',%s)
           ON CONFLICT (release_id) DO NOTHING""",
        (
            plan["release_id"],
            plan["model_version"],
            plan["dataset"],
            plan["model_sha256"],
            plan["scores_sha256"],
            plan["source_database_sha256"],
            plan["threshold"],
            plan["transaction_rows"],
            plan["positive_rows"],
            plan["triggered_rows"],
            plan["feature_count"],
            Jsonb(plan["benchmark"]),
            Jsonb(plan["policy"]),
            datetime.now(tz=UTC),
        ),
    )

    # Bảng tạm rồi nối theo source_transaction_id: parquet dùng mã băm của bộ dữ
    # liệu gốc, PostgreSQL đánh số bằng bigint.
    pg.execute("DROP TABLE IF EXISTS stage_edge_scores")
    pg.execute(
        """CREATE TEMP TABLE stage_edge_scores (
               source_transaction_id TEXT, model_score DOUBLE PRECISION,
               threshold DOUBLE PRECISION, triggered BOOLEAN
           )"""
    )
    con = duckdb.connect()
    try:
        with pg.cursor().copy("COPY stage_edge_scores FROM STDIN WITH (FORMAT CSV)") as copy:
            for batch in con.execute(
                """SELECT transaction_id, score, threshold, triggered
                     FROM read_parquet(?)""",
                [str(scores)],
            ).to_arrow_reader(200_000):
                for row in batch.to_pylist():
                    copy.write(
                        f"{row['transaction_id']},{row['score']},{row['threshold']},"
                        f"{'true' if row['triggered'] else 'false'}\n"
                    )
    finally:
        con.close()

    inserted = pg.execute(
        """INSERT INTO transaction_model_score (release_id, transaction_id, model_score, threshold, triggered)
           SELECT %s, t.transaction_id, s.model_score, s.threshold, s.triggered
             FROM stage_edge_scores s
             JOIN transaction t USING (source_transaction_id)
           ON CONFLICT DO NOTHING""",
        (plan["release_id"],),
    ).rowcount
    staged = pg.execute("SELECT count(*) FROM stage_edge_scores").fetchone()[0]
    pg.execute("DROP TABLE stage_edge_scores")

    # Đúng một bản phát hành được hoạt động tại một thời điểm.
    pg.execute("UPDATE edge_model_release SET status='superseded' WHERE status='active'")
    pg.execute(
        "UPDATE edge_model_release SET status='active', activated_at=now() WHERE release_id=%s",
        (plan["release_id"],),
    )
    pg.commit()
    return {
        "status": "active",
        "release_id": plan["release_id"],
        "staged": int(staged),
        "scores_linked": int(inserted),
        "unmatched": int(staged) - int(inserted),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(args)
    if args.dry_run:
        print(
            json.dumps(
                {"dry_run": True, "plan": {k: v for k, v in plan.items() if k != "policy"}},
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return 0

    url = _psycopg_url(args.database_url or get_settings().database_url)
    with psycopg.connect(url) as pg:
        result = load(pg, plan, args.scores)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if result.get("unmatched"):
        print(
            f"CẢNH BÁO: {result['unmatched']} dòng điểm không nối được với giao dịch nào trong "
            "PostgreSQL. Thường là do parquet và cơ sở dữ liệu đến từ hai ảnh chụp khác nhau.",
            flush=True,
        )
    print("Bước cuối — dựng lại rollup địa lý:", flush=True)
    print("  python scripts/load_bank_geography.py --accounts data/raw/ibm-aml/LI-Small_accounts.csv", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
