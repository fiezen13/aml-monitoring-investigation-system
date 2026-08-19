"""Suy luận Bitcoin AML — nạp mô hình MỘT LẦN, chấm bằng ``predict_proba``.

Tách hẳn khỏi huấn luyện: không đọc lại dữ liệu huấn luyện, không huấn luyện
lại. Nạp artifact (mô hình + metadata đặc trưng), kiểm tra đầu vào khớp đúng số
lượng và thứ tự đặc trưng đã chốt lúc huấn luyện, rồi trả bằng chứng có cấu trúc
cho tác tử.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib

from src.bitcoin_aml.config import BitcoinAmlConfig, get_bitcoin_config
from src.bitcoin_aml.explain import build_explanation
from src.bitcoin_aml.model import illicit_probability
from src.bitcoin_aml.schemas import (
    BitcoinAmlResult,
    Decision,
    FeatureContribution,
    Prediction,
    PredictionEvidence,
    TransactionFeatures,
)

logger = logging.getLogger("fin07.bitcoin_aml.inference")

#: Số đặc trưng đầu bảng đính vào phần bằng chứng của mỗi dự đoán.
TOP_FEATURE_COUNT = 5


class ModelNotTrainedError(Exception):
    """Artifact mô hình chưa tồn tại — cần chạy pipeline huấn luyện trước."""


class BitcoinAmlPredictor:
    """Bộ suy luận đã nạp sẵn artifact. Dựng một lần rồi tái sử dụng.

    An toàn để giữ như singleton trong tiến trình: ``RandomForestClassifier`` chỉ
    đọc khi ``predict_proba``, không có trạng thái thay đổi giữa các lần gọi.
    """

    def __init__(self, config: BitcoinAmlConfig | None = None) -> None:
        self.config = config or get_bitcoin_config()
        if not self.config.model_path.exists():
            raise ModelNotTrainedError(
                f"Không thấy artifact mô hình tại {self.config.model_path}. Chạy: python -m scripts.train_bitcoin_aml"
            )
        self.model = joblib.load(self.config.model_path)
        metadata = json.loads(Path(self.config.feature_metadata_path).read_text(encoding="utf-8"))
        self.selected_features: list[str] = list(metadata["selected_features"])
        self.feature_importance: dict[str, float] = dict(metadata.get("feature_importance", {}))
        self.model_id: str = metadata.get("model_id", "bitcoin-ellipticpp-rf-v1")
        self.model_name: str = metadata.get("algorithm", "random_forest_feature_refinement")
        self.thresholds = self.config.thresholds
        logger.info("Nạp Bitcoin AML: %d đặc trưng, model_id=%s", len(self.selected_features), self.model_id)

    @property
    def feature_count(self) -> int:
        return len(self.selected_features)

    def _validate(self, item: TransactionFeatures) -> None:
        if len(item.features) != self.feature_count:
            raise ValueError(
                f"Giao dịch {item.transaction_id}: nhận {len(item.features)} đặc trưng, "
                f"mô hình cần đúng {self.feature_count} theo thứ tự đã chốt lúc huấn luyện."
            )

    def _evidence(self, item: TransactionFeatures) -> PredictionEvidence:
        # Đính đặc trưng quan trọng NHẤT của rừng kèm giá trị của chính giao dịch.
        # importance là độ quan trọng TOÀN CỤC (impurity), không phải đóng góp
        # riêng cho giao dịch này — không giả vờ là SHAP.
        ranked = sorted(
            self.selected_features,
            key=lambda name: self.feature_importance.get(name, 0.0),
            reverse=True,
        )[:TOP_FEATURE_COUNT]
        value_of = dict(zip(self.selected_features, item.features, strict=True))
        top = [
            FeatureContribution(
                feature=name,
                value=float(value_of[name]),
                importance=self.feature_importance.get(name),
            )
            for name in ranked
        ]
        return PredictionEvidence(timestep=item.timestep, top_features=top, pattern_evidence=[])

    def _build_result(self, item: TransactionFeatures, score: float) -> BitcoinAmlResult:
        """Dựng kết quả đầy đủ từ một điểm số — chấm đơn và chấm lô dùng chung.

        Gộp một chỗ để prediction/decision/explanation không lệch nhau giữa hai
        đường gọi.
        """
        label = "illicit" if score >= 0.5 else "licit"
        # confidence = độ tự tin về nhãn ĐƯỢC chọn: xa 0.5 là chắc, gần 0.5 là lưỡng lự.
        confidence = score if label == "illicit" else 1.0 - score
        level = self.thresholds.level(score)
        prediction = Prediction(label=label, risk_score=round(score, 6), confidence=round(confidence, 6))
        feature_values = dict(zip(self.selected_features, item.features, strict=True))
        return BitcoinAmlResult(
            model=self.model_name,
            model_id=self.model_id,
            transaction_id=item.transaction_id,
            prediction=prediction,
            evidence=self._evidence(item),
            decision=Decision(risk_level=level, requires_review=level in ("HIGH", "CRITICAL")),
            explanation=build_explanation(feature_values, self.feature_importance, prediction),
        )

    def predict_one(self, item: TransactionFeatures) -> BitcoinAmlResult:
        """Chấm một giao dịch, kèm bằng chứng có cấu trúc và giải thích đời thường."""
        self._validate(item)
        score = illicit_probability(self.model, [item.features])[0]
        return self._build_result(item, score)

    def predict_batch(self, items: list[TransactionFeatures]) -> list[BitcoinAmlResult]:
        """Chấm nhiều giao dịch trong MỘT lượt ``predict_proba`` (vector hoá).

        Không lặp gọi mô hình từng dòng: gom cả lô rồi chấm một lần, rẻ hơn nhiều
        khi hàng nghìn giao dịch.
        """
        for item in items:
            self._validate(item)
        matrix = [item.features for item in items]
        scores = illicit_probability(self.model, matrix)
        return [self._build_result(item, score) for item, score in zip(items, scores, strict=True)]
