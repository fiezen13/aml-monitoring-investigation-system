#!/usr/bin/env python3
"""Chốt benchmark của nhánh SAML-D geo_rule vào bảng ``edge_model_release``.

    python scripts/build_geo_rule_release.py

Vì sao cần
----------
Hai nhánh của hệ thống — IBM HI-Medium (MEGA-PNA, rửa tiền trong ngân hàng) và
SAML-D (geo_rule, rửa tiền xuyên biên giới) — mỗi nhánh có model và benchmark
riêng, đo trên đúng VÙNG mà nó đặc trưng. Không có một con số chung, vì hai
model dùng hai loại chỉ số khác nhau: MEGA-PNA chấm từng cạnh (F1, PR-AUC),
geo_rule xếp hạng theo ngân sách cảnh báo (precision/recall/lift @ budget).

Benchmark của IBM đã nằm trong ``edge_model_release`` cùng lô với mã băm mô hình.
Benchmark của SAML-D thì mới chỉ nằm ở ``reports/geo-rule/saml_d_v1.json`` —
giao diện không đọc được, nên nhánh này vô hình. Script đọc report ấy rồi ghi
vào đúng release row, để giao diện trình bày hai nhánh cạnh nhau, mỗi nhánh trên
vùng của mình.

Không huấn luyện gì ở đây: geo_rule là bộ luật, trọng số hành lang đo trên
train+validation rồi áp lên test. Script chỉ đóng gói kết quả đã có.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "REL-GEO-SAMLD-V1"
MODEL_VERSION = "geo-rule-saml-d-v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=ROOT / "reports/geo-rule/saml_d_v1.json")
    p.add_argument("--container", default="fin07-postgres-1")
    p.add_argument("--database", default="fin07_hi_medium")
    p.add_argument("--db-user", default="fin07")
    return p.parse_args()


def psql(args: argparse.Namespace, statement: str, *, stdin: str | None = None) -> str:
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
        input=stdin,
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        print(proc.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout.strip()


def main() -> int:
    args = parse_args()
    if not args.report.exists():
        print(f"Không thấy {args.report}", file=sys.stderr)
        return 1
    report = json.loads(args.report.read_text(encoding="utf-8"))

    # Benchmark chuẩn hoá cho giao diện: cùng khung với IBM ở phần
    # ``operating_points`` (alerts/caught/precision/recall), nhưng khai rõ đây là
    # bộ chỉ số của bộ xếp hạng theo ngân sách, và VÙNG đo là giao dịch xuyên
    # biên giới — không phải toàn bộ giao dịch.
    positive = int(report["test_positive_cells_cross_border"])
    region_rows = int(report["test_cells_cross_border"])
    benchmark = {
        "schema_version": "fin07.geo_rule.release.v1",
        "model_kind": "geo_rule_ranker",
        "region_label": "Giao dịch xuyên biên giới",
        "region_description": (
            "Chỉ đo trên các ô (tài khoản, cửa sổ) có giao dịch xuyên biên giới — vùng mà nhánh này đặc "
            "trưng. Giao dịch nội địa không thuộc phạm vi của bộ luật địa lý."
        ),
        "region_rows": region_rows,
        "region_all_rows": int(report["test_cells_all"]),
        "positive_rows": positive,
        "positive_rate": float(report["test_positive_rate_cross_border"]),
        "window_days": int(report["window_days"]),
        # geo_rule không có F1/PR-AUC: nó xếp hạng, nên chỉ số đầu bảng là
        # precision/recall/lift tại một ngân sách cảnh báo cụ thể. Lấy mốc 250
        # cảnh báo làm điểm trình bày — cùng cỡ với hàng đợi rà soát một ngày.
        "operating_points": report["operational_budget"],
        "top_corridors": report.get("top_corridors", []),
        "note": report.get("note", ""),
        "not_comparable_note": (
            "Không so trực tiếp với nhánh IBM: khác vùng (xuyên biên giới vs toàn bộ giao dịch trong "
            "ngân hàng), khác loại model (bộ luật xếp hạng vs mạng đồ thị chấm cạnh), khác bộ chỉ số."
        ),
    }

    fingerprint = hashlib.sha256(json.dumps(benchmark, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    total_rows = int(report["test_cells_all"])
    # triggered_rows = số cảnh báo geo_rule thực mở, đọc từ bảng alert.
    triggered = int(psql(args, "SELECT count(*) FROM alert WHERE detector='geo_rule'") or "0")

    payload = json.dumps(benchmark, ensure_ascii=False)
    # status='reference': đây là nhánh song song, không phải bản đang chấm điểm
    # cho hàng đợi chính. Giao diện hiện cả 'active' lẫn 'reference'.
    psql(
        args,
        """INSERT INTO edge_model_release
             (release_id, model_version, dataset, split, model_sha256, scores_sha256,
              source_database_sha256, threshold, transaction_rows, positive_rows,
              triggered_rows, feature_count, benchmark, policy, status, trained_at)
           VALUES (:rid, :mv, 'SAML-D', 'test', :sha, :sha, repeat('0',64),
                   0, :txrows, :pos, :trig, 4, :bm::jsonb,
                   '{"rule_based": true, "trained": false}'::jsonb, 'reference', now())
           ON CONFLICT (release_id) DO UPDATE
             SET benchmark = EXCLUDED.benchmark, model_sha256 = EXCLUDED.model_sha256,
                 scores_sha256 = EXCLUDED.scores_sha256, transaction_rows = EXCLUDED.transaction_rows,
                 positive_rows = EXCLUDED.positive_rows, triggered_rows = EXCLUDED.triggered_rows""".replace(
            ":rid", f"'{RELEASE_ID}'"
        )
        .replace(":mv", f"'{MODEL_VERSION}'")
        .replace(":sha", f"'{fingerprint}'")
        .replace(":txrows", str(total_rows))
        .replace(":pos", str(positive))
        .replace(":trig", str(triggered))
        .replace(":bm", f"$${payload}$$"),
    )
    print(
        f"đã chốt {RELEASE_ID}: vùng xuyên biên giới {region_rows:,} ô · {positive:,} dương · "
        f"{triggered:,} cảnh báo · fingerprint {fingerprint[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
