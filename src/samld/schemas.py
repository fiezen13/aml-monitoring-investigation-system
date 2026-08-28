"""Hợp đồng đầu ra nhánh SAML-D — cho API và Agent.

Model CHỈ trả xác suất AML + ngữ cảnh giao dịch. TUYỆT ĐỐI không trả FATF /
sanctions / country risk (đó là kiến thức tuân thủ ngoài model, do World Monitor
cung cấp riêng). Agent nhận model_evidence và world_monitor_evidence độc lập.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TransactionContext(BaseModel):
    """Sự thật giao dịch + ngữ cảnh dẫn xuất — KHÔNG có điểm rủi ro nào."""

    sender_account: str
    receiver_account: str
    amount: float
    sender_country: str
    receiver_country: str
    cross_border: bool
    payment_currency: str
    received_currency: str
    currency_mismatch: bool
    payment_type: str


class ModelSignal(BaseModel):
    """Tín hiệu tất định từ đặc trưng model/giao dịch (không phải LLM bịa)."""

    type: str  # cross_border | currency_mismatch | network_anomaly | ...
    value: float | bool


class SamldResult(BaseModel):
    """Kết quả một giao dịch từ nhánh SAML-D."""

    transaction_id: str
    detector: Literal["samld_graph"] = "samld_graph"
    dataset: Literal["SAML-D"] = "SAML-D"
    model: str = "samld_multi_pna_eu"
    #: P(laundering) từ softmax của model đồ thị. KHÔNG cộng gộp với nhánh khác.
    aml_probability: float = Field(ge=0.0, le=1.0)
    prediction: Literal["suspicious", "normal"]
    threshold: float
    transaction_context: TransactionContext
    #: Bằng chứng MODEL (tất định). Bằng chứng compliance (FATF…) nằm ở nguồn khác.
    model_evidence: list[ModelSignal] = Field(default_factory=list)


class SamldAgentInput(BaseModel):
    """Gói đưa cho Agent — tách rõ model evidence với world-monitor evidence."""

    source: Literal["samld"] = "samld"
    model_result: dict
    transaction: TransactionContext
    model_evidence: list[ModelSignal] = Field(default_factory=list)
    #: Do World Monitor điền (FATF/sanctions/jurisdiction) — model KHÔNG tự suy.
    world_monitor_evidence: list[dict] = Field(default_factory=list)
