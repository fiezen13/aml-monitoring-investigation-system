#!/usr/bin/env python3
"""Chốt nhánh Bitcoin AML thành một release để giao diện hiện thẻ nhánh thứ ba.

    python -m scripts.build_bitcoin_release

Đọc artifact do ``scripts.train_bitcoin_aml`` sinh ra, rồi ghi một dòng vào
``edge_model_release`` với ``model_kind`` = 'random_forest_classifier' và
``region_label`` = 'Giao dịch Bitcoin'. Endpoint /fc/model-branches tự nhặt dòng
này lên, nên thẻ nhánh Bitcoin xuất hiện cạnh IBM và SAML-D mà không sửa giao
diện.

Nhánh này ĐỘC LẬP: không hợp nhất điểm với hai nhánh kia, chỉ đứng cạnh để đối
chiếu theo vùng đặc trưng (giao dịch Bitcoin, dữ liệu Elliptic++).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bitcoin_aml.config import get_bitcoin_config  # noqa: E402

RELEASE_ID = "REL-BTC-ELLIPTICPP-V1"
MODEL_VERSION = "bitcoin-ellipticpp-rf-v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--container", default="fin07-postgres-1")
    p.add_argument("--database", default="fin07_hi_medium")
    p.add_argument("--db-user", default="fin07")
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
    config = get_bitcoin_config()
    if not config.metrics_path.exists() or not config.model_metadata_path.exists():
        print(
            f"Chưa có artifact tại {config.artifact_dir}. Chạy trước: python -m scripts.train_bitcoin_aml",
            file=sys.stderr,
        )
        return 1

    metrics = json.loads(config.metrics_path.read_text(encoding="utf-8"))
    model_meta = json.loads(config.model_metadata_path.read_text(encoding="utf-8"))
    repro = model_meta["reproducibility"]
    test = metrics["test"]

    region_rows = int(repro["test_samples"])
    positive = int(test["support_illicit"])

    benchmark = {
        "schema_version": "fin07.bitcoin_aml.release.v1",
        "model_kind": "random_forest_classifier",
        "region_label": "Giao dịch Bitcoin",
        "region_description": (
            "Đo trên tập test theo thời gian của Elliptic++ (các bước thời gian muộn nhất) — "
            "vùng mà nhánh này đặc trưng: giao dịch trên mạng Bitcoin, phát hiện illicit/licit."
        ),
        "region_rows": region_rows,
        "positive_rows": positive,
        "positive_rate": (positive / region_rows) if region_rows else None,
        # RF là bộ phân loại từng giao dịch, nên chỉ số đầu bảng giống họ F1/PR-AUC
        # của nhánh IBM — nhưng đo trên VÙNG khác và bằng model khác.
        "primary_seed": {
            "f1": test["f1_illicit"],
            "pr_auc": test["pr_auc"],
            "precision": test["precision_illicit"],
            "recall": test["recall_illicit"],
            "roc_auc": test["roc_auc"],
        },
        "operating_points": metrics.get("operating_points", []),
        "reference": model_meta["reference"],
        "note": (
            "Random Forest + tinh gọn đặc trưng, tái lập paper Elliptic++ (ACM SIGKDD 2023). "
            "Chia theo thời gian, unknown bị loại khỏi tập giám sát."
        ),
        "not_comparable_note": (
            "Không so trực tiếp với IBM hay SAML-D: khác vùng (giao dịch Bitcoin vs giao dịch ngân "
            "hàng vs xuyên biên giới), khác bộ dữ liệu, khác model. Mỗi nhánh đánh giá độc lập."
        ),
    }
    fingerprint = hashlib.sha256(json.dumps(benchmark, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    payload = json.dumps(benchmark, ensure_ascii=False)

    psql(
        args,
        """INSERT INTO edge_model_release
             (release_id, model_version, dataset, split, model_sha256, scores_sha256,
              source_database_sha256, threshold, transaction_rows, positive_rows,
              triggered_rows, feature_count, benchmark, policy, status, trained_at)
           VALUES (:rid, :mv, 'Elliptic++', 'test', :sha, :sha, repeat('0',64),
                   0.5, :rows, :pos, 0, :fc, :bm::jsonb,
                   '{"rule_based": false, "trained": true, "temporal_split": true}'::jsonb,
                   'reference', now())
           ON CONFLICT (release_id) DO UPDATE
             SET benchmark = EXCLUDED.benchmark, model_sha256 = EXCLUDED.model_sha256,
                 scores_sha256 = EXCLUDED.scores_sha256, transaction_rows = EXCLUDED.transaction_rows,
                 positive_rows = EXCLUDED.positive_rows, feature_count = EXCLUDED.feature_count""".replace(
            ":rid", f"'{RELEASE_ID}'"
        )
        .replace(":mv", f"'{MODEL_VERSION}'")
        .replace(":sha", f"'{fingerprint}'")
        .replace(":rows", str(region_rows))
        .replace(":pos", str(positive))
        .replace(":fc", str(int(repro["feature_count"])))
        .replace(":bm", f"$${payload}$$"),
    )
    print(
        f"đã chốt {RELEASE_ID}: vùng Bitcoin {region_rows:,} giao dịch test · {positive:,} illicit · "
        f"F1={test['f1_illicit']:.4f} · fingerprint {fingerprint[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
