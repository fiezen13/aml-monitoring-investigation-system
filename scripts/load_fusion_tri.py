#!/usr/bin/env python3
"""Nạp bản hợp nhất ba nhánh vào ảnh chụp đặc trưng đang phục vụ.

Hộp 5 của sơ đồ kiến trúc chỉ "sống" trên giao diện khi
``behavior_feature_snapshot.features`` mang đủ ba thành phần: ``get_risk_breakdown``
đọc từ đó để giải thích điểm cho chuyên viên.

Script này cập nhật ảnh chụp đang phục vụ (mốc lớn nhất trong
``behavior_feature_snapshot``) bằng phân vị và mức đóng góp của cả ba nhánh, đặt
``champion = 'fusion'``, rồi tạo cảnh báo cho những dòng vượt ngưỡng.

Không đụng vào ``transaction``, không đụng vào cảnh báo của ba nhánh đơn.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402
from src.investigation.typology_match import match_typology, signals_from_graph_motifs  # noqa: E402
from src.services.if_alert_publish import record_typology_match  # noqa: E402

DEFAULT_SCORES = ROOT / "data/processed/fusion-tri/tri_fusion_scores.parquet"
DEFAULT_BUNDLE = ROOT / "models/fin07_rule_if_graph_fusion_v1.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))

    with get_session() as session:
        as_of = session.execute(text("SELECT max(as_of_time) FROM behavior_feature_snapshot")).scalar_one_or_none()
        if as_of is None:
            raise SystemExit("Chưa có behavior_feature_snapshot; chạy load_fusion_release.py trước.")

        con = duckdb.connect()
        rows = con.execute(
            """SELECT account_key, rule_percentile, isolation_forest_percentile, graph_percentile,
                      rule_contribution, isolation_forest_contribution, graph_contribution,
                      fusion_score, fusion_threshold, triggered,
                      fan_in_hit, fan_out_hit, gather_scatter_hit, cycle_hit
                 FROM read_parquet(?)
                WHERE as_of_ts = ?::TIMESTAMPTZ""",
            [str(args.scores), as_of.isoformat()],
        ).fetchall()
        con.close()

        if not rows:
            raise SystemExit(f"Không có dòng hợp nhất nào cho mốc {as_of.isoformat()}")

        print(f"[1/3] {len(rows):,} tài khoản tại mốc {as_of:%Y-%m-%d}", flush=True)
        if args.dry_run:
            print(
                json.dumps({"dry_run": True, "rows": len(rows), "triggered": sum(1 for r in rows if r[9])}, indent=2),
                flush=True,
            )
            return 0

        # Bổ sung ba thành phần vào ảnh chụp. Ghi đè `champion` thành 'fusion' để
        # `get_risk_breakdown` báo `fusion_available = true`.
        payload = [
            {
                "account": r[0],
                "as_of": as_of,
                "patch": json.dumps(
                    {
                        "rule_percentile": r[1],
                        "isolation_forest_percentile": r[2],
                        "graph_percentile": r[3],
                        "rule_contribution": r[4],
                        "isolation_forest_contribution": r[5],
                        "graph_contribution": r[6],
                        "fusion_score": r[7],
                        "fusion_threshold": r[8],
                        "champion": "fusion",
                        "fusion_branches": ["rule", "isolation_forest", "graph"],
                        "fusion_weights": bundle["weights"],
                    }
                ),
            }
            for r in rows
        ]
        session.execute(
            text(
                """UPDATE behavior_feature_snapshot
                      SET features = features || CAST(:patch AS jsonb)
                    WHERE account_key = :account AND as_of_time = :as_of"""
            ),
            payload,
        )
        print("[2/3] Đã cập nhật ảnh chụp đặc trưng", flush=True)

        created = 0
        for r in rows:
            if not r[9]:
                continue
            account, score = r[0], float(r[7])
            alert_id = (
                "ALT-TRI-"
                + __import__("hashlib")
                .sha1(f"{account}|{as_of.isoformat()}|{bundle['fusion_version']}".encode())
                .hexdigest()[:16]
            )
            if session.execute(text("SELECT 1 FROM alert WHERE alert_id = :a"), {"a": alert_id}).scalar_one_or_none():
                continue
            match = match_typology(
                signals_from_graph_motifs(
                    {"fan_in_hit": r[10], "fan_out_hit": r[11], "gather_scatter_hit": r[12], "cycle_hit": r[13]}
                )
            )
            session.execute(
                text(
                    """INSERT INTO alert (alert_id, account_key, transaction_id, typology_code,
                                          detector, risk_score, status, case_id, created_at)
                       VALUES (:a, :k, NULL, :t, 'graph', :s, 'open', NULL, :d)"""
                ),
                {
                    "a": alert_id,
                    "k": account,
                    "t": match.typology_code,
                    "s": round(min(max(score, 0.0), 1.0) * 100, 2),
                    "d": as_of,
                },
            )
            for code, label, value, weight in (
                ("FUSION_RULE", "Đóng góp nhánh luật", r[4], bundle["weights"]["rule"]),
                ("FUSION_ANOMALY", "Đóng góp nhánh bất thường", r[5], bundle["weights"]["isolation_forest"]),
                ("FUSION_GRAPH", "Đóng góp nhánh đồ thị", r[6], bundle["weights"]["graph"]),
            ):
                session.execute(
                    text(
                        """INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
                           VALUES (:a, :c, :l, :v, :w) ON CONFLICT DO NOTHING"""
                    ),
                    {
                        "a": alert_id,
                        "c": code,
                        "l": label,
                        "v": round(float(value) * 100, 2),
                        "w": round(float(weight), 2),
                    },
                )
            record_typology_match(session, alert_id, match)
            created += 1

        print(f"[3/3] Tạo {created:,} cảnh báo hợp nhất", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
