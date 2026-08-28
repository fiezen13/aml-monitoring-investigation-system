"""Nạp kết quả benchmark SAML-D (Multi-PNA+EU) vào ``edge_model_release``.

Đọc ``artifacts/samld/overall_metrics.json`` (do scripts.samld_benchmark sinh)
và chốt một release ``REL-GRAPH-SAMLD-V1`` (status='reference') để nó hiện ở
``/fc/model-branches`` và trang Đánh giá chuẩn. KHÔNG cộng gộp điểm với IBM/Elliptic.

Chạy (sau khi có artifacts):
    python -m scripts.build_samld_release --container fin07-postgres-1 --database fin07_hi_medium
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from src.samld.config import get_samld_config

RELEASE_ID = "REL-GRAPH-SAMLD-V1"
MODEL_VERSION = "samld-multi-pna-eu-v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Chốt release SAML-D Multi-PNA+EU vào DB.")
    p.add_argument("--container", default="fin07-postgres-1")
    p.add_argument("--db-user", default="fin07")
    p.add_argument("--database", default="fin07_hi_medium")
    return p.parse_args()


def psql(args: argparse.Namespace, statement: str) -> str:
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


def main() -> int:
    args = parse_args()
    cfg = get_samld_config()
    overall_path = cfg.artifact_dir / "overall_metrics.json"
    if not overall_path.exists():
        print(f"Chưa có {overall_path}. Chạy trước: python -m scripts.samld_benchmark", file=sys.stderr)
        return 1

    overall = json.loads(overall_path.read_text(encoding="utf-8"))
    m = overall["main_metrics"]
    region_rows = int(overall.get("region_rows", m["rows"]))
    positive = int(overall.get("positive_rows", m["positives"]))
    cm = m["confusion_matrix"]
    triggered = int(cm["tp"] + cm["fp"])  # số cạnh vượt ngưỡng vận hành

    benchmark = {
        "schema_version": "fin07.samld.release.v1",
        "model_kind": "graph_edge_classifier",
        "region_label": "Giao dịch ngân hàng SAML-D",
        "region_description": (
            "Đo trên tập test theo thời gian của SAML-D (giai đoạn muộn nhất) — vùng nhánh này "
            "đặc trưng: giao dịch ngân hàng trên bộ SAML-D, phân loại cạnh trên đồ thị "
            "tài khoản bằng Multi-PNA+EU."
        ),
        "region_rows": region_rows,
        "positive_rows": positive,
        "positive_rate": (positive / region_rows) if region_rows else None,
        "primary_seed": {
            "f1": m["f1"],
            "pr_auc": m["pr_auc"],
            "precision": m["precision"],
            "recall": m["recall"],
        },
        "over_seeds": overall.get("over_seeds", {}),
        "operating_points": overall.get("operating_points", []),
        "not_comparable_note": (
            "Đo trên VÙNG SAML-D, bằng model đồ thị; không so trực tiếp với IBM (MEGA-PNA) hay "
            "Elliptic (Random Forest) — ba nhánh đánh giá độc lập."
        ),
    }
    payload = json.dumps(benchmark, ensure_ascii=False)
    threshold = float(overall["operational_threshold"])
    # feature_count phải > 0 (ràng buộc DB) — số đặc trưng CẠNH đã encode.
    feature_count = int(overall.get("edge_features", 1))

    stmt = (
        """INSERT INTO edge_model_release
             (release_id, model_version, dataset, split, model_sha256, scores_sha256,
              source_database_sha256, threshold, transaction_rows, positive_rows,
              triggered_rows, feature_count, benchmark, policy, status, trained_at)
           VALUES (:rid, :mv, 'SAML-D', 'test', repeat('0',64), repeat('0',64), repeat('0',64),
                   :thr, :rows, :pos, :trig, :fc, :bm::jsonb,
                   '{"rule_based": false, "trained": true, "temporal_split": true, "graph_model": true}'::jsonb,
                   'reference', now())
           ON CONFLICT (release_id) DO UPDATE
             SET benchmark = EXCLUDED.benchmark, threshold = EXCLUDED.threshold,
                 transaction_rows = EXCLUDED.transaction_rows, positive_rows = EXCLUDED.positive_rows,
                 triggered_rows = EXCLUDED.triggered_rows, feature_count = EXCLUDED.feature_count""".replace(
            ":rid", f"'{RELEASE_ID}'"
        )
        .replace(":mv", f"'{MODEL_VERSION}'")
        .replace(":thr", f"{threshold:.6f}")
        .replace(":rows", str(region_rows))
        .replace(":pos", str(positive))
        .replace(":trig", str(triggered))
        .replace(":fc", str(max(1, feature_count)))
        .replace(":bm", f"$${payload}$$")
    )
    psql(args, stmt)
    print(
        f"đã chốt {RELEASE_ID}: SAML-D {region_rows:,} giao dịch test · {positive:,} dương · "
        f"F1={m['f1']:.4f} · PR-AUC={m['pr_auc']:.4f} · ngưỡng {threshold:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
