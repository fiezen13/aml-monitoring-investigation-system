from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvestigationStatus(StrEnum):
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    FAILED = "FAILED"


class WorkflowState(StrEnum):
    INITIALIZED = "INITIALIZED"
    COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
    EXPLAINING = "EXPLAINING"
    VALIDATING = "VALIDATING"
    COMPOSING_REPORT = "COMPOSING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceType(StrEnum):
    RISK_BREAKDOWN = "RISK_BREAKDOWN"
    RULE_TRIGGER = "RULE_TRIGGER"
    BEHAVIOR_FEATURE = "BEHAVIOR_FEATURE"
    ANOMALY_EXPLANATION = "ANOMALY_EXPLANATION"
    TRANSACTION = "TRANSACTION"
    GRAPH_PATTERN = "GRAPH_PATTERN"
    GRAPH_NEIGHBORHOOD = "GRAPH_NEIGHBORHOOD"
    TYPOLOGY_MAPPING = "TYPOLOGY_MAPPING"


class EvidenceIntegrity(BaseModel):
    source_system: str
    source_record_ids: list[str] = Field(default_factory=list)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceEnvelope(BaseModel):
    evidence_id: str
    type: EvidenceType
    source: str
    account_key: str
    payload: dict[str, Any]
    transaction_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    integrity: EvidenceIntegrity
    is_untrusted_content: bool = False


class RiskComponent(BaseModel):
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)
    available: bool = True
    source_ref: str | None = None


class RiskBreakdown(BaseModel):
    alert_id: str
    final_risk_score: float = Field(ge=0, le=1)
    score_scale: Literal["0-1"] = "0-1"
    fusion_available: bool
    components: dict[str, RiskComponent]
    source_of_truth: Literal["detection_engine"] = "detection_engine"
    limitation: str | None = None


class ObservedActivity(BaseModel):
    """Analyst-facing aggregates in original units.

    ``BehaviorResult.features`` is the model feature vector: amounts there are
    log1p-transformed and unusable in a sentence a reviewer has to read. These
    are the same window measured in currency, counts and hours, so an
    explanation can quote a number the reviewer recognizes.
    """

    window_start: datetime
    window_end: datetime
    # Stated as a number because "7d" alone leaves the claim "cửa sổ 7 ngày"
    # with no numeric source, and the critic then flags a correct sentence.
    window_days: int = Field(gt=0)
    currency: str | None = None
    inflow_amount: float = Field(ge=0)
    outflow_amount: float = Field(ge=0)
    largest_amount: float = Field(ge=0)
    incoming_count: int = Field(ge=0)
    outgoing_count: int = Field(ge=0)
    unique_in_counterparties: int = Field(ge=0)
    unique_out_counterparties: int = Field(ge=0)
    new_counterparties: int = Field(ge=0)
    rapid_outflow_amount: float = Field(ge=0)
    rapid_outflow_percent: float = Field(ge=0, le=100)
    rapid_window_hours: int = 2
    median_dwell_hours: float | None = None
    active_days: int = Field(ge=0)


class BehaviorResult(BaseModel):
    account_key: str
    window: str
    as_of_time: datetime
    feature_definition_version: str
    features: dict[str, float | int]
    observed: ObservedActivity | None = None


class TransactionRecord(BaseModel):
    transaction_id: str
    source: str
    destination: str
    timestamp: datetime
    amount: float = Field(gt=0)
    currency: str
    payment_format: str


class TransactionPage(BaseModel):
    items: list[TransactionRecord]
    limit: int
    next_cursor: str | None = None
    truncated: bool


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_account: str = Field(alias="from")
    to_account: str = Field(alias="to")
    transaction_id: str


class GraphEvidenceResult(BaseModel):
    evidence_id: str | None = None
    pattern: str | None = None
    accounts: list[str] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    cycle_length: int | None = None
    duration_hours: float | None = None
    available: bool
    missing_reason: str | None = None


class GraphNeighborhoodResult(BaseModel):
    account_key: str
    hops: int
    nodes: list[str]
    edges: list[GraphEdge]
    truncated: bool


class TypologyAssignment(BaseModel):
    """Mã nhóm hành vi này là kết luận hay chỉ là giá trị mặc định.

    Tác tử phản biện dùng trường ``is_fallback`` để biết có được phép coi nhóm
    hành vi như một dữ kiện hay không. Thiếu nó, mọi cảnh báo đều mang T02 và
    mọi câu nhắc tới T02 đều trở thành nhận định không có bằng chứng.
    """

    typology_code: str
    is_fallback: bool
    observed_signals: list[str] = Field(default_factory=list)
    matched_required: list[str] = Field(default_factory=list)
    matched_supporting: list[str] = Field(default_factory=list)
    rationale: str = ""


class TypologyResult(BaseModel):
    pattern: str
    typology_code: str
    name: str
    description: str
    required_signals: list[str]
    supporting_signals: list[str]
    version: str
    # Bản tiếng Việt dùng cho mọi câu chữ hiển thị cho chuyên viên. Tên và mô tả
    # tiếng Anh vẫn giữ nguyên vì là khoá đối chiếu với danh mục gốc.
    name_vi: str = ""
    description_vi: str = ""
    signal_labels_vi: dict[str, str] = Field(default_factory=dict)
    # Dấu vết ánh xạ cho chính cảnh báo đang điều tra, lấy từ
    # ``alert_typology_match``. Không có bản ghi thì để None — nghĩa là cảnh báo
    # có từ trước khi bật ánh xạ, chưa rõ mã đến từ đâu.
    assignment: TypologyAssignment | None = None


class AnomalousFeature(BaseModel):
    feature: str
    value: float
    reference_percentile: float = Field(ge=0, le=100)
    source_ref: str


class AnomalyExplanationResult(BaseModel):
    account_key: str
    anomaly_score: float = Field(ge=0, le=1)
    top_anomalous_features: list[AnomalousFeature]
    method: str
    available: bool
    missing_reason: str | None = None


class Claim(BaseModel):
    claim_id: str
    claim: str = Field(min_length=1, max_length=4096)
    claim_type: Literal["FACT", "INFERENCE"]
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def facts_require_evidence(self) -> Claim:
        if self.claim_type == "FACT" and not self.evidence_refs:
            raise ValueError("Nhận định loại DỮ KIỆN cần ít nhất một tham chiếu bằng chứng")
        return self


class RiskDriver(BaseModel):
    #: Nhánh sinh ra phần điểm này.
    #:
    #: `mega_pna` thêm vào khi mô hình đồ thị thay chỗ Isolation Forest. Ràng
    #: buộc cũ chỉ có ba giá trị và Pydantic từ chối bản ghi ngay ở tầng lược
    #: đồ — sau khi đã sửa hai chỗ khác, đây là chốt thứ ba cùng một nguyên nhân:
    #: danh sách nhánh bị viết cứng ở nhiều nơi thay vì một chỗ.
    source: Literal["rule", "anomaly", "graph", "mega_pna", "geo_rule"]
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)
    reason: str
    evidence_refs: list[str]


class Explanation(BaseModel):
    summary: str
    risk_drivers: list[RiskDriver]
    claims: list[Claim]
    facts: list[str]
    inferences: list[str]
    missing_information: list[str]
    typologies: list[str]
    confidence: float = Field(ge=0, le=1)
    recommended_action: Literal[
        "CONTINUE_MONITORING",
        "REQUEST_MORE_INFORMATION",
        "ESCALATE_TO_L2",
        "REVIEW_FOR_SAR_STR",
        "CLOSE_AS_LIKELY_FALSE_POSITIVE",
    ]
    requires_human_review: Literal[True] = True


class ValidationIssue(BaseModel):
    type: Literal[
        "MISSING_EVIDENCE",
        "UNSUPPORTED_CLAIM",
        "CONTRADICTION",
        "INVALID_SCORE_CONTRIBUTION",
        "MISSING_SOURCE_RECORD",
        "INVALID_TYPOLOGY",
        "OTHER",
    ]
    claim: str
    evidence_ref: str | None = None
    required_tool: str | None = None
    detail: str


class ValidationResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    confidence: float = Field(ge=0, le=1)
    issues: list[ValidationIssue] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    next_action: Literal["RETURN_TO_INVESTIGATION", "BUILD_CASE_PACKAGE"]


class ToolArguments(BaseModel):
    """Closed Gemini response schema spanning the seven allow-listed tools."""

    model_config = ConfigDict(extra="forbid")

    alert_id: str | None = None
    account_key: str | None = None
    counterparty: str | None = None
    transaction_ids: list[str] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    direction: Literal["in", "out"] | None = None
    limit: int | None = None
    cursor: str | None = None
    window: Literal["1d", "7d", "30d", "90d"] | None = None
    time_window: Literal["1d", "7d", "30d", "90d"] | None = None
    hops: int | None = None
    pattern: str | None = None
    typology_code: str | None = None


class ToolDecision(BaseModel):
    tool: Literal[
        "GetRiskBreakdown",
        "GetAccountBehavior",
        "GetTransactions",
        "GetGraphEvidence",
        "GetGraphNeighborhood",
        "GetTypology",
        "GetAnomalyExplanation",
    ]
    arguments: ToolArguments
    short_rationale: str


class SupervisorPlan(BaseModel):
    decisions: list[ToolDecision]
    open_questions: list[str]
    evidence_sufficient: bool


class TraceEvent(BaseModel):
    trace_id: str
    investigation_id: str
    agent: str
    event_type: str
    tool: str | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_ref: str | None = None
    short_rationale: str = ""
    model_name: str | None = None
    prompt_version: str | None = None
    occurred_at: datetime


class InvestigationOut(BaseModel):
    investigation_id: str
    alert_id: str
    case_id: str
    account_key: str
    status: InvestigationStatus
    workflow_state: WorkflowState
    iteration: int
    tool_call_count: int
    snapshot_time: datetime
    risk_summary: dict[str, Any]
    accounts_expanded: list[str]
    open_questions: list[str]
    validation: ValidationResult | None = None
    failure_reason: str | None = None
    human_review: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class InvestigationStartOut(BaseModel):
    investigation_id: str
    alert_id: str
    case_id: str
    job_id: str
    status: Literal["QUEUED"] = "QUEUED"


class ReviewRequest(BaseModel):
    decision: Literal[
        "CONTINUE_MONITORING",
        "REQUEST_MORE_INFORMATION",
        "ESCALATE_TO_L2",
        "REVIEW_FOR_SAR_STR",
        "CLOSE_AS_LIKELY_FALSE_POSITIVE",
    ]
    reason: str = Field(min_length=10, max_length=2000)


class InvestigationPackage(BaseModel):
    investigation_id: str
    account: str
    risk: dict[str, Any]
    executive_summary: str
    primary_risk_drivers: list[RiskDriver]
    behavior_findings: list[str]
    graph_findings: list[str]
    rule_findings: list[str]
    typologies: list[str]
    evidence_refs: list[str]
    missing_information: list[str]
    recommended_next_step: str
    requires_human_review: Literal[True] = True


class ReviewFeedbackOut(BaseModel):
    """Một nhãn do chuyên viên tạo ra, kèm ảnh chụp điểm lúc ra quyết định.

    ``risk_score`` là điểm tại thời điểm rà soát chứ không phải điểm hiện tại của
    cảnh báo: nạp một bản phát hành mới sẽ đổi điểm, và khi đó cặp (nhãn, điểm)
    dùng để hiệu chỉnh ngưỡng sẽ sai nếu đọc điểm hiện hành.
    """

    feedback_id: str
    investigation_id: str
    alert_id: str | None = None
    case_id: str | None = None
    account_key: str
    decision: str
    label: Literal["SUSPICIOUS", "NOT_SUSPICIOUS", "INCONCLUSIVE"]
    reason: str = ""
    risk_score: float | None = None
    detector: str | None = None
    typology_code: str | None = None
    #: True nghĩa là nhóm hành vi đi kèm nhãn này chỉ là giá trị mặc định.
    typology_was_fallback: bool | None = None
    investigation_status: str
    reviewed_by: str
    reviewed_at: datetime


class ReviewFeedbackPage(BaseModel):
    total: int
    items: list[ReviewFeedbackOut]
