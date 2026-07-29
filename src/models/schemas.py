from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")


class CaseOut(BaseModel):
    case_id: str
    subject_account_key: str
    title: str
    state: str
    risk_score: Decimal
    priority: str
    assigned_to: str | None = None
    created_at: datetime
    alert_count: int


class AlertReasonOut(BaseModel):
    """Một yếu tố đóng góp vào điểm rủi ro.

    NT7 — mỗi điểm rủi ro kèm danh sách yếu tố đóng góp và trọng số, hiển thị được.
    """

    factor_code: str
    factor_label: str
    contribution: Decimal
    weight: Decimal
    detector: str
    typology_code: str


class CaseDetailOut(CaseOut):
    evidence_count: int
    reasons: list[AlertReasonOut]


class QueueStatsOut(BaseModel):
    depth: int = Field(description="Số tác vụ đang chờ trong hàng đợi")
    worker_alive: bool = Field(description="Có worker nào còn ghi nhịp tim không")


class HealthOut(BaseModel):
    status: str
    env: str


class ReadyOut(BaseModel):
    status: str
    database: bool
    redis: bool
