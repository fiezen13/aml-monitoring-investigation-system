"""Đường ống huấn luyện nhánh Bitcoin AML — một hàm gọi được từ CLI và test.

    nạp dữ liệu → kiểm cột → lọc nhãn → chia theo thời gian → tinh gọn đặc trưng
    → huấn luyện Random Forest → đánh giá → lưu mô hình + metadata + chỉ số

Không có bước nào chạy lúc backend khởi động: đây là quy trình ngoại tuyến, gọi
qua ``python -m scripts.train_bitcoin_aml``.
"""

from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone
from typing import Any

import joblib
import sklearn

from src.bitcoin_aml.config import BitcoinAmlConfig, get_bitcoin_config
from src.bitcoin_aml.data import load_elliptic, temporal_split
from src.bitcoin_aml.evaluate import budget_curve, evaluate_split
from src.bitcoin_aml.features import apply_selection, importance_lookup, refine_features
from src.bitcoin_aml.model import build_model, illicit_probability, train_model

logger = logging.getLogger("fin07.bitcoin_aml.training")

UTC = timezone.utc  # noqa: UP017
MODEL_ID = "bitcoin-ellipticpp-rf-v1"
ALGORITHM = "random_forest_feature_refinement"

REFERENCE = {
    "title": ("Demystifying Fraudulent Transactions and Illicit Nodes in the Bitcoin Network for Financial Forensics"),
    "authors": ["Youssef Elmougy", "Ling Liu"],
    "venue": "ACM SIGKDD",
    "year": 2023,
    "doi": "10.1145/3580305.3599803",
    "dataset_repo": "https://github.com/git-disl/EllipticPlusPlus",
}


def train_pipeline(config: BitcoinAmlConfig | None = None) -> dict[str, Any]:
    """Chạy trọn đường ống, ghi artifact, trả về khối chỉ số + metadata.

    Trả về dict để test và release builder dùng lại mà không đọc file.
    """
    config = config or get_bitcoin_config()
    config.artifact_dir.mkdir(parents=True, exist_ok=True)

    loaded = load_elliptic(config)
    split = temporal_split(loaded, config)

    selected, ranking = refine_features(split, config)
    refined = apply_selection(split, selected)
    importance = importance_lookup(ranking)

    # Huấn luyện và suy luận cùng dùng MẢNG numpy (không tên cột), để mô hình
    # đã học không kỳ vọng tên đặc trưng — API chỉ gửi vector số, không gửi tên.
    x_train = refined.x_train.to_numpy()
    x_val = refined.x_val.to_numpy()
    x_test = refined.x_test.to_numpy()
    model = train_model(build_model(config), x_train, refined.y_train)

    metrics = {
        "model": "elliptic_plus_plus_random_forest",
        "validation": evaluate_split(model, x_val, refined.y_val, split_name="validation"),
        "test": evaluate_split(model, x_test, refined.y_test, split_name="test"),
    }
    # Chỉ số đầu bảng (illicit trên test) đưa lên cùng cấp cho dễ đọc — vẫn là
    # con số của chính lần chạy này, không hard-code.
    metrics.update(
        {
            "precision_illicit": metrics["test"]["precision_illicit"],
            "recall_illicit": metrics["test"]["recall_illicit"],
            "f1_illicit": metrics["test"]["f1_illicit"],
            "roc_auc": metrics["test"]["roc_auc"],
            "pr_auc": metrics["test"]["pr_auc"],
        }
    )
    # Đường vận hành theo ngân sách cảnh báo trên test — cùng khuôn với hai nhánh
    # kia, để thẻ nhánh trên giao diện đọc song song. Tính từ chính điểm test.
    test_scores = illicit_probability(model, x_test)
    metrics["operating_points"] = budget_curve(test_scores, [int(v) for v in refined.y_test])

    feature_metadata = {
        "model_id": MODEL_ID,
        "algorithm": ALGORITHM,
        "selected_features": selected,
        "feature_count_full": len(loaded.feature_names),
        "feature_count_selected": len(selected),
        "feature_importance": {name: importance[name] for name in selected},
        "feature_ranking": ranking,
        "id_column": loaded.id_column,
        "time_column": loaded.time_column,
    }

    model_metadata = {
        "model_id": MODEL_ID,
        "domain": "bitcoin",
        "task": "illicit_transaction_detection",
        "dataset": "Elliptic++",
        "algorithm": "RandomForestClassifier",
        "reference": REFERENCE,
        "reproducibility": {
            "python_version": platform.python_version(),
            "sklearn_version": sklearn.__version__,
            "trained_at": datetime.now(UTC).isoformat(),
            "random_seed": config.random_seed,
            "feature_count": len(selected),
            "training_samples": int(len(refined.x_train)),
            "validation_samples": int(len(refined.x_val)),
            "test_samples": int(len(refined.x_test)),
            "class_distribution": loaded.class_distribution,
            "train_timesteps": split.train_timesteps,
            "test_timesteps": split.test_timesteps,
            "hyperparameters": {
                "n_estimators": config.n_estimators,
                "max_depth": config.max_depth,
                "max_features": config.max_features,
                "min_samples_leaf": config.min_samples_leaf,
                "class_weight": config.class_weight,
            },
        },
        "thresholds": {
            "medium": config.thresholds.medium,
            "high": config.thresholds.high,
            "critical": config.thresholds.critical,
        },
    }

    # Ghi artifact. Mô hình nén để file nhỏ; ba file metadata JSON đọc được bằng mắt.
    joblib.dump(model, config.model_path, compress=3)
    config.feature_metadata_path.write_text(
        json.dumps(feature_metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    config.metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    config.model_metadata_path.write_text(json.dumps(model_metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Đã lưu artifact vào %s — F1 illicit (test) = %.4f",
        config.artifact_dir,
        metrics["f1_illicit"],
    )
    return {"metrics": metrics, "feature_metadata": feature_metadata, "model_metadata": model_metadata}
