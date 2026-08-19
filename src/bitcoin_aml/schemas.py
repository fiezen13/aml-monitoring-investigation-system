"""Lược đồ đầu vào/đầu ra của nhánh Bitcoin AML.

Đầu ra giàu ngữ nghĩa để tác tử dùng được ngay — không chỉ ``{"prediction": 1}``.
Mọi giá trị đều bắt nguồn từ ``predict_proba`` của mô hình thật; không có trường
nào bịa. Ngữ nghĩa đặc trưng KHÔNG được đặt tên: Elliptic++ ẩn danh hoá đặc
trưng, nên chỉ giữ index/tên gốc, không gọi ``feature_71 = mixer_score``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
IllicitLabel = Literal["illicit", "licit"]


class TransactionFeatures(BaseModel):
    """Một giao dịch cần chấm: mã và vector đặc trưng theo đúng thứ tự đã chọn.

    ``features`` phải khớp về SỐ LƯỢNG và THỨ TỰ với danh sách đặc trưng đã tinh
    gọn lúc huấn luyện (``feature_metadata.json``). Bộ suy luận kiểm tra điều này
    và từ chối vector sai chiều, thay vì chấm bừa.
    """

    transaction_id: str = Field(min_length=1, max_length=128)
    features: list[float] = Field(min_length=1)
    timestep: int | None = Field(default=None, ge=1)


class BatchPredictRequest(BaseModel):
    transactions: list[TransactionFeatures] = Field(min_length=1, max_length=5000)


class FeatureContribution(BaseModel):
    """Một đặc trưng và giá trị của nó trong giao dịch được chấm.

    ``feature`` là tên/index GỐC của Elliptic++, không phải nhãn ngữ nghĩa bịa ra.
    ``importance`` là độ quan trọng toàn cục của rừng (impurity), không phải đóng
    góp riêng cho giao dịch này — nói rõ để không ngộ nhận là SHAP.
    """

    feature: str
    value: float
    importance: float | None = None


class Prediction(BaseModel):
    label: IllicitLabel
    #: P(illicit | giao dịch), lấy thẳng từ predict_proba. KHÔNG cộng với điểm
    #: của nhánh IBM hay SAML-D — mỗi nhánh chấm riêng.
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class PredictionEvidence(BaseModel):
    timestep: int | None = None
    top_features: list[FeatureContribution] = Field(default_factory=list)
    #: Chỗ mở rộng cho phát hiện mẫu hình sau này. Elliptic++ KHÔNG cung cấp nhãn
    #: fan-in/fan-out/layering, nên để trống thay vì bịa mẫu hình.
    pattern_evidence: list[dict] = Field(default_factory=list)


class Decision(BaseModel):
    risk_level: RiskLevel
    requires_review: bool


class BitcoinExplanation(BaseModel):
    """Giải thích đời thường cho chuyên viên non-tech.

    ``headline`` một câu tóm tắt; ``reasons`` các ý cụ thể từ đặc trưng ĐỌC ĐƯỢC
    (số địa chỉ gửi/nhận, số BTC, phí…); ``caveat`` nói thẳng phần căn cứ là đặc
    trưng ẩn danh và không có nhãn mẫu hình — để không ngộ nhận.
    """

    headline: str
    reasons: list[str] = Field(default_factory=list)
    caveat: str


class BitcoinAmlResult(BaseModel):
    """Kết quả một giao dịch — đúng dạng bằng chứng có cấu trúc cho tác tử.

    ``detector`` / ``domain`` / ``dataset`` tách bạch nhánh này khỏi hai nhánh
    kia trong mắt tác tử: nó nhận riêng banking / bitcoin / country, không có một
    điểm gộp toàn cục nào ở tầng mô hình.
    """

    detector: Literal["bitcoin_aml"] = "bitcoin_aml"
    domain: Literal["bitcoin"] = "bitcoin"
    dataset: Literal["elliptic++"] = "elliptic++"
    model: str
    model_id: str
    entity_type: Literal["transaction"] = "transaction"
    transaction_id: str

    prediction: Prediction
    evidence: PredictionEvidence
    decision: Decision
    #: Giải thích đời thường cho chuyên viên — trung thực, không bịa mẫu hình.
    explanation: BitcoinExplanation


class BatchPredictResponse(BaseModel):
    model: str
    model_id: str
    count: int
    results: list[BitcoinAmlResult]
