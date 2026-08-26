from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    # Bộ dữ liệu của cảnh báo. Hàng đợi phục vụ nhiều bộ, và một cảnh báo SAML-D
    # đứng cạnh một cảnh báo IBM mà không có nhãn thì không ai phân biệt được.
    dataset: str = "ibm_hi_medium"


class AlertPageOut(BaseModel):
    """Một trang cảnh báo; `total` luôn là tổng sau bộ lọc, không phải cỡ trang."""

    rows: list[AlertOut]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = ConfigDict(populate_by_name=True)


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


class CaseBandOut(BaseModel):
    """Số vụ việc theo dải điểm rủi ro (critical/high/medium/low)."""

    band: str
    count: int


class CaseAgeOut(BaseModel):
    """Số vụ việc theo tuổi hồ sơ (lt1d/d1_7/d7_30/gt30d)."""

    bucket: str
    count: int


class DashboardOut(BaseModel):
    """Số liệu Trung tâm Điều hành — đếm thật từ PostgreSQL, không cứng hoá."""

    open_alerts: int
    high_risk_alerts: int
    cases_investigating: int
    sar_pending: int
    avg_risk_score: float
    latest_batch_id: str | None
    latest_source_name: str | None
    transactions_analyzed: int
    subjects_analyzed: int
    subjects_below_threshold: int
    subjects_triggered: int
    batch_alerts_created: int
    typology_distribution: list[TypologyShareOut]
    top_alerts: list[AlertOut]
    queue_depth: int
    worker_alive: bool
    # Số liệu VỤ VIỆC cho dashboard theo vai trò (đếm thật, lọc theo dataset).
    case_risk_bands: list[CaseBandOut] = Field(default_factory=list)
    case_age_buckets: list[CaseAgeOut] = Field(default_factory=list)
    cases_unassigned: int = 0
    cases_total: int = 0


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
    gemini_configured: bool


class ReadyOut(BaseModel):
    status: str
    database: bool
    redis: bool
    gemini_configured: bool


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    email: str
    role: str
    role_label: str = Field(alias="roleLabel")
    active: bool
    last_login: datetime | None = Field(default=None, alias="lastLogin")
    #: Quyền + phạm vi dữ liệu do MÁY CHỦ tính từ vai trò (nguồn sự thật cho RBAC
    #: giao diện). Frontend đọc từ đây, không tự suy từ role trong localStorage.
    permissions: list[str] = Field(default_factory=list)
    data_scope: str = Field(default="assigned", alias="dataScope")


class LoginOut(BaseModel):
    token: str
    user: UserOut


class SarActionRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|more_info)$")
    reason: str = Field(..., min_length=10, max_length=2000)


class SarChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(default="", max_length=4000)


class SarChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[SarChatMessage] = Field(default_factory=list, max_length=12)


class SettingUpdateRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=10, max_length=2000)


class UserUpdateRequest(BaseModel):
    active: bool
    reason: str = Field(..., min_length=10, max_length=2000)


class InternalAlertReasonIn(BaseModel):
    """Mot factor cho alert IF (NT7 can >= 3)."""

    factor_code: str = Field(..., min_length=1, max_length=64)
    factor_label: str = Field(..., min_length=1, max_length=500)
    contribution: float = Field(..., ge=0, le=100)
    weight: float = Field(default=0.35, ge=0, le=1)


class InternalAlertCreate(BaseModel):
    """Body POST /api/v1/internal/alerts — ingest alert detector=ml."""

    account_key: str = Field(..., min_length=3, max_length=128)
    risk_score: float = Field(..., ge=0, le=100, description="Thang 0-100 (UI/DB)")
    # Bỏ trống để hệ thống suy nhóm hành vi từ ``features`` theo danh mục
    # typologies.json. Chỉ điền khi cần ép cứng một mã.
    typology_code: str | None = Field(default=None, pattern=r"^T(0[1-9]|10)$")
    reasons: list[InternalAlertReasonIn] = Field(..., min_length=3)
    features: dict[str, float] | None = Field(
        default=None,
        description="Vector đặc trưng hành vi; dùng để suy nhóm hành vi",
    )
    alert_id: str | None = Field(default=None, max_length=64)
    as_of_ts: datetime | None = None
    window: str = Field(default="7d", pattern=r"^(1d|7d)$")
    model_version: str = Field(default="if_baseline_7d_v1", max_length=64)


class InternalAlertCreateOut(BaseModel):
    alert_id: str
    created: bool
    subjects_created: bool
    risk_score: float | None = None
    factor_count: int | None = None
    detector: str = "ml"
