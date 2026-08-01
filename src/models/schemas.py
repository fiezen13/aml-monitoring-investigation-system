from datetime import date, datetime
from decimal import Decimal
from typing import Any

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


class CustomerOut(BaseModel):
    """Hồ sơ chủ thể đứng sau một tài khoản.

    Không có trường họ tên: lược đồ cố ý không lưu tên khách hàng (dữ liệu
    tổng hợp, xem COMMENT của bảng customer). Giao diện định danh chủ thể
    bằng `customer_id` và mô tả bằng nghề nghiệp/nguyên mẫu.
    """

    customer_id: str
    account_key: str
    customer_type: str
    prototype: str
    occupation: str
    declared_income_band: str
    expected_monthly_volume: Decimal
    registered_country: str
    risk_rating: str
    onboarding_date: date
    account_status: str
    bank_code: str


class AlertOut(BaseModel):
    """Một dòng trong hàng đợi cảnh báo."""

    alert_id: str
    account_key: str
    customer_id: str
    occupation: str
    risk_rating: str
    typology_code: str
    typology_label: str
    detector: str
    risk_score: Decimal
    status: str
    case_id: str | None = None
    created_at: datetime
    factor_count: int


class TransactionOut(BaseModel):
    transaction_id: int
    occurred_at: datetime
    from_account_key: str
    to_account_key: str
    amount: Decimal
    currency: str
    channel: str
    direction: str = Field(description="`in` khi tiền vào tài khoản chủ thể, `out` khi đi ra")


class AlertDetailOut(AlertOut):
    """Chi tiết cảnh báo — NT7: luôn kèm tối thiểu ba yếu tố đóng góp."""

    customer: CustomerOut
    reasons: list[AlertReasonOut]
    transactions: list[TransactionOut]
    case_state: str | None = None


class CaseTimelineStepOut(BaseModel):
    """Một bước trên máy trạng thái điều tra (ARC-001 Hình 4)."""

    state: str
    label: str
    status: str = Field(description="done | active | pending")
    occurred_at: datetime | None = None


class CaseDetailOut(CaseOut):
    evidence_count: int
    reasons: list[AlertReasonOut]
    customer: CustomerOut | None = None
    timeline: list[CaseTimelineStepOut] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)


class AuditEventOut(BaseModel):
    """Một dòng nhật ký kiểm toán. Bảng chỉ ghi thêm (NT4, QD6)."""

    audit_id: int
    case_id: str | None = None
    event_type: str
    actor: str
    actor_role: str
    payload: dict[str, Any]
    occurred_at: datetime


class TypologyShareOut(BaseModel):
    typology_code: str
    typology_label: str
    alert_count: int
    share_pct: float


class DashboardOut(BaseModel):
    """Số liệu Trung tâm Điều hành — đếm thật từ PostgreSQL, không cứng hoá."""

    open_alerts: int
    high_risk_alerts: int
    cases_investigating: int
    sar_pending: int
    avg_risk_score: float
    typology_distribution: list[TypologyShareOut]
    top_alerts: list[AlertOut]
    queue_depth: int
    worker_alive: bool


class InvestigateOut(BaseModel):
    job_id: str
    case_id: str
    status: str
    state_before: str


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
