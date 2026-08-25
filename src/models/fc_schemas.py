"""Hợp đồng dữ liệu cho các màn hình "Thành phố tài chính".

Tách khỏi `schemas.py` vì hai nhóm phục vụ hai thứ khác nhau: `schemas.py` là
quy trình AML đang vận hành (cảnh báo, vụ việc, SAR, phê duyệt), còn file này
là dữ liệu do mô phỏng ABM sinh ra theo tài liệu thiết kế v2.0.

Quy ước chung với phần còn lại của API: NUMERIC của PostgreSQL đi qua JSON
dưới dạng chuỗi, nên các trường tiền tệ khai báo là `float` và được ép kiểu ở
tầng truy vấn, chứ không để Decimal rơi ra ngoài.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------
# World Monitor
# ---------------------------------------------------------------------


class HubOut(BaseModel):
    id: str
    name: str
    country: str
    lat: float
    lon: float
    jurisdiction_risk: str
    # Các số liệu tổng hợp từ corridor_flow, không lưu sẵn trong bảng hub.
    inbound: int = 0
    outbound: int = 0
    volume_usd: float = 0
    alerts: int = 0
    entities: int = 0
    risk_score: int = 0


class FlowOut(BaseModel):
    id: str
    source_hub: str
    target_hub: str
    source_name: str
    target_name: str
    slat: float
    slon: float
    tlat: float
    tlon: float
    channel: str
    currency: str
    amount_native: float
    volume_usd: float
    txn_count: int
    risk_score: int
    typology_hint: str | None
    alert_count: int
    first_seen: datetime
    last_seen: datetime


class WorldOut(BaseModel):
    hubs: list[HubOut]
    flows: list[FlowOut]
    simulation_id: str | None
    scenario_package: str | None
    data_mode: Literal["operational"]
    source_id: str | None
    source_name: str | None
    transaction_count: int = 0
    geography_available: bool
    limitation: str | None


# ---------------------------------------------------------------------
# Đồ thị thực thể
# ---------------------------------------------------------------------


class GraphNodeOut(BaseModel):
    id: str
    type: str
    label: str
    sub: str
    risk: int
    first: datetime
    last: datetime
    hub: str | None
    # Thực thể hợp pháp cố ý đưa vào để đo tỷ lệ dương tính giả (hard negative).
    negative: bool = False


class GraphEdgeOut(BaseModel):
    # Định danh ổn định của cạnh. Cần cho việc chọn cạnh rồi hỏi sổ cái xem
    # cạnh đó gồm những giao dịch nào — trước đây cạnh không có id nên phía
    # giao diện phải tự ghép chuỗi từ hai đầu.
    id: str
    s: str
    t: str
    kind: str
    label: str
    amt: float | None
    # Ba trường dưới đây là lý do đồ thị này dùng được cho điều tra: chúng nói
    # rõ cạnh nào là quan sát trực tiếp, cạnh nào là suy luận và suy từ đâu.
    inferred: bool
    conf: float | None
    logic: str | None
    known_from: datetime

    # --- Chứng cứ giao dịch ---------------------------------------------
    # Ba trường dưới đây KHÔNG đến từ `fc.relationship` mà được tổng hợp từ
    # bảng `transaction` thật. Một cạnh là *quan hệ*, còn giao dịch là *sự
    # kiện*; đồ thị chỉ được vẽ quan hệ, và mỗi quan hệ phải chỉ ra được nó
    # dựa trên bao nhiêu sự kiện nào.
    #
    # `tx_count = 0` là một câu trả lời hợp lệ và hay gặp: quan hệ sở hữu, dùng
    # chung thiết bị hay chuyển trên chuỗi vốn không có giao dịch ngân hàng nào
    # đứng sau. Giao diện phải nói thẳng "không có bằng chứng giao dịch" chứ
    # không được bịa ra một con số.
    tx_count: int = 0
    # Không cộng nhiều loại tiền vào một số. Khoá là mã ISO, giá trị là tổng
    # theo đúng loại tiền đó.
    amounts_by_currency: dict[str, float] = Field(default_factory=dict)
    tx_first_seen: datetime | None = None
    tx_last_seen: datetime | None = None


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class PatternHopOut(BaseModel):
    """Một chặng trong mẫu hình, kèm số liệu tra được từ sổ giao dịch."""

    seq: int
    source: str
    target: str
    transaction_id: str
    occurred_at: datetime | None = None
    amount: float | None = None
    currency: str | None = None
    #: Khoảng cách tới chặng trước, tính bằng giờ. Đây là con số nói lên tốc độ
    #: luân chuyển — thứ chuyên viên dùng để đánh giá mức đáng ngờ.
    gap_hours: float | None = None


class DetectedPatternOut(BaseModel):
    """Một mẫu hình do bộ dò đồ thị tìm được, dựng thành trình tự đọc được.

    Trang đồ thị trước đây đếm chu trình bằng cách dò trên **vùng đang vẽ** — một
    lân cận một chặng quanh tài khoản có cảnh báo, gần như luôn là hình sao nên
    không bao giờ có chu trình. Nó hiện "Chu trình: 0" trong khi cơ sở dữ liệu có
    72 chu trình đã dò được. Endpoint này trả đúng những mẫu hình ấy.
    """

    evidence_id: str
    pattern: str
    account_key: str
    accounts: list[str]
    hop_count: int
    duration_hours: float | None = None
    detector_version: str
    as_of_time: datetime
    hops: list[PatternHopOut]


# ---------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------


class CryptoTransferOut(BaseModel):
    id: str
    chain: str
    tx_hash: str
    from_address: str
    to_address: str
    asset: str
    amount: float
    amount_usd: float | None
    block_time: datetime
    kind: str
    link_confidence: float | None


class ExposureOut(BaseModel):
    address: str
    service_id: str
    service_type: str
    exposure_kind: str
    hops: int
    confidence: float
    source_id: str
    known_from: datetime


class CryptoOut(BaseModel):
    transfers: list[CryptoTransferOut]
    exposures: list[ExposureOut]
    total_usd: float
    source_mode: Literal["on_chain", "ledger"] = "on_chain"


class ProjectOut(BaseModel):
    id: str
    name: str
    symbol: str
    chain: str
    contract_address: str
    deployer_address: str
    launched_at: datetime
    holder_gini: float | None
    liquidity_usd: float
    liquidity_removed_pct: float | None
    privileged_functions: list[str]
    kol_channels: int
    domain_age_days: int | None
    risk_score: int
    status: str


# ---------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------


class AgentStepOut(BaseModel):
    id: str
    index: int
    tool: str
    input_summary: str
    output_summary: str
    status: str
    started_at: datetime
    duration_ms: int
    evidence_refs: list[str]


class AgentRunOut(BaseModel):
    id: str
    case_id: str | None
    alert_id: str | None
    tier: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    model_version: str
    conclusion: str
    confidence: float | None
    token_cost: int
    step_count: int = 0


class AgentRunDetailOut(AgentRunOut):
    steps: list[AgentStepOut]


class AgentRunListOut(BaseModel):
    """Danh sách lượt chạy (giới hạn để hiển thị) KÈM tổng thật từ toàn bảng.

    Trước đây endpoint trả list rỗng có LIMIT 200, và giao diện đếm ``rows.length``
    → khi có >200 lượt thì thẻ "Tổng lần chạy" LUÔN kẹt ở 200. Các số tổng phải
    tính bằng aggregate trên toàn bảng, không phải đếm số dòng lấy về.
    """

    rows: list[AgentRunOut]
    total: int
    critic_count: int
    failed_count: int
    total_tokens: int


# ---------------------------------------------------------------------
# Kiểm định, giám sát, chất lượng dữ liệu
# ---------------------------------------------------------------------


class BenchmarkOut(BaseModel):
    id: str
    task_id: str
    scenario_package: str
    model_version: str
    split: str
    metric_name: str
    metric_value: float
    target_value: float | None
    evaluated_at: datetime
    # Suy ở tầng API để giao diện không phải lặp lại logic so sánh ngưỡng;
    # riêng false_positive_rate thì thấp mới là đạt.
    passed: bool | None = None


class ModelMonitorOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    observed_at: datetime
    metric_name: str
    metric_value: float
    drift_score: float | None
    status: str


class DataQualityOut(BaseModel):
    id: str
    dataset: str
    check_name: str
    dimension: str
    observed_at: datetime
    pass_rate: float
    threshold: float
    rows_checked: int
    rows_failed: int
    status: str
    detail: str


class ObservationOut(BaseModel):
    id: str
    evidence_item_id: str
    observer_role: str
    available_from: datetime
    acquisition_type: str
    legal_basis_id: str | None
    redaction_profile: str
    source_confidence: float
    chain_of_custody_id: str | None
    is_visible_to_model: bool
    summary: str


class SourceOut(BaseModel):
    source_id: str
    source_type: str
    scope: str
    period: str
    jurisdiction: str
    confidence: float
    access_level: str
    prohibited_uses: str


# ---------------------------------------------------------------------
# Tổng hợp cho shell và Transaction Explorer
# ---------------------------------------------------------------------


class NavCountsOut(BaseModel):
    alerts: int
    approvals: int
    critical: int
    # Kỳ dữ liệu đang hiển thị, lấy từ chính bảng transaction. Header cần nó để
    # nói rõ người dùng đang nhìn khoảng thời gian nào — thay cho bộ chọn
    # 1h/24h/7d/30d cũ, vốn không nối vào truy vấn nào.
    data_period_start: date | None = None
    data_period_end: date | None = None


class SearchHitOut(BaseModel):
    id: str
    label: str
    kind: str
    href: str


class TxRowOut(BaseModel):
    id: int
    source_id: str | None = None
    occurred_at: datetime
    from_account: str
    to_account: str
    amount: float
    currency: str
    amount_received: float | None = None
    receiving_currency: str | None = None
    channel: str
    remarks: str
    model_score: float | None = None
    threshold: float | None = None
    triggered: bool | None = None
    model_version: str | None = None
    # Nhãn rửa tiền chỉ đi kèm khi người gọi có quyền kiểm định; mặc định None.
    is_laundering: bool | None = None


class TxPageOut(BaseModel):
    rows: list[TxRowOut]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = ConfigDict(populate_by_name=True)


class EdgeModelReleaseOut(BaseModel):
    release_id: str
    model_version: str
    dataset: str
    split: str
    model_sha256: str
    scores_sha256: str
    source_database_sha256: str
    threshold: float
    transaction_rows: int
    positive_rows: int
    triggered_rows: int
    feature_count: int
    benchmark: dict[str, Any]
    policy: dict[str, Any]
    status: str
    trained_at: datetime
    activated_at: datetime | None


class GraphNarrativeOut(BaseModel):
    """Bản kể của tác tử cho một vùng đồ thị.

    Màn hình đồ thị vẽ đúng nhưng không giải thích gì: chuyên viên nhìn vào một
    mớ đỉnh và mũi tên rồi phải tự trả lời tiền vào từ đâu, đi đâu, ai đứng
    giữa, vì sao đáng nghi. Bốn trường dưới đây là bốn câu trả lời ấy.

    ``source`` cho biết bản kể do mô hình viết hay do phần đo tự dựng. Đây là
    thông tin của kiểm toán, và cũng để chuyên viên biết mình đang đọc gì.
    """

    account_key: str
    window_start: datetime
    window_end: datetime
    flow_in: str
    flow_out: str
    why_suspicious: list[str]
    how_to_read: list[str]
    source: Literal["gemini", "deterministic"]
    reading: dict[str, Any]


class OperatingPointOut(BaseModel):
    """Một điểm vận hành: cho một ngân sách cảnh báo, bắt được bao nhiêu.

    Cả hai nhánh đều dùng chung dạng này, nên giao diện vẽ được một đường
    precision/recall theo ngân sách cho từng nhánh mà không cần biết bên trong
    là model gì. ``lift`` chỉ có ở nhánh xếp hạng (geo_rule); để None cho nhánh
    chấm cạnh (MEGA-PNA) vì lift không phải chỉ số của nó.
    """

    alerts: int
    caught: int
    precision: float
    recall: float
    lift: float | None = None


class ModelBranchOut(BaseModel):
    """Một nhánh phát hiện, kèm benchmark đo trên đúng VÙNG nó đặc trưng.

    Ba nhánh của hệ thống — IBM HI-Medium (rửa tiền trong ngân hàng), SAML-D
    (xuyên biên giới), Elliptic (bitcoin) — mỗi nhánh có model và benchmark
    riêng. Chúng KHÔNG cộng gộp được: khác vùng, khác loại model, khác bộ chỉ
    số. Schema này cố tình để mỗi nhánh tự khai vùng và loại model của mình,
    thay vì ép một con số chung.
    """

    release_id: str
    dataset: str
    model_version: str
    model_kind: str
    region_label: str
    region_description: str
    region_rows: int | None = None
    positive_rows: int | None = None
    positive_rate: float | None = None
    triggered_rows: int
    status: str
    #: Chỉ số đầu bảng, đã chọn sẵn cho từng loại model (F1/PR-AUC cho MEGA-PNA,
    #: precision/recall/lift @ ngân sách cho geo_rule). Nhãn kèm sẵn để hiển thị.
    headline: list[dict[str, Any]]
    operating_points: list[OperatingPointOut]
    note: str | None = None
    not_comparable_note: str | None = None


# ---------------------------------------------------------------------
# Nhánh Bitcoin (Elliptic) — trình bày vận hành.
#
# Elliptic ẩn danh: chỉ có mã giao dịch và đặc trưng che tên, không địa chỉ /
# tài khoản / nhãn dịch vụ. Nên nhánh này KHÔNG dùng khuôn cảnh báo–tài khoản
# của IBM/SAML-D; nó là một hàng đợi giao dịch bị Random Forest chấm nghi ngờ,
# đọc từ bảng ``bitcoin_scored_tx`` (điểm tập test, chấm sẵn bằng script).
# ---------------------------------------------------------------------
class BitcoinNeighbourOut(BaseModel):
    """Một láng giềng 1 chặng trên đồ thị giao dịch Bitcoin."""

    id: str
    #: 'in' (gửi tới giao dịch này), 'out' (nhận từ nó), 'both'.
    dir: str
    #: MODEL DỰ ĐOÁN: true = model gắn cờ; false = không; null = ngoài tập đã chấm.
    flag: bool | None = None
    #: GROUND TRUTH: true = có NHÃN THẬT bất hợp pháp (Elliptic). Khác hẳn `flag`.
    known_illicit: bool = False


class BitcoinDriverOut(BaseModel):
    """Một đặc trưng và đóng góp của nó vào điểm của CHÍNH giao dịch này (Saabas)."""

    name: str
    #: Nhãn tiếng Việt nếu đặc trưng ĐỌC ĐƯỢC; null nếu ẩn danh (không bịa nghĩa).
    label: str | None = None
    meaningful: bool
    value: float
    #: Đóng góp có dấu vào P(illicit): dương = đẩy về nghi ngờ, âm = kéo về bình thường.
    contribution: float


class EvidenceReasonOut(BaseModel):
    """Một lý do TẤT ĐỊNH kèm badge nguồn (GROUND_TRUTH/GRAPH/MODEL/PREDICTION/…)."""

    priority: int
    badges: list[str] = Field(default_factory=list)
    title: str
    text: str


class RiskReasonReference(BaseModel):
    population: str  # training_reference
    percentile: int | None = None


class RiskReasonOut(BaseModel):
    id: str
    category: str
    title: str
    side: str  # local | upstream | downstream | upstream_tx | downstream_tx
    feature_ids: list[int] = Field(default_factory=list)
    reference: RiskReasonReference | None = None
    shap_direction: str  # increase_risk | decrease_risk
    contribution: str  # very_high | high | medium | low
    contribution_label: str  # RẤT MẠNH | MẠNH | VỪA | THẤP
    temporal_availability: str  # available_at_transaction_time | after_transaction
    after_transaction: bool = False
    investigator_text: str


class BitcoinScoredRowOut(BaseModel):
    tx_id: str
    timestep: int | None = None
    #: P(illicit) từ predict_proba. Không cộng gộp với điểm nhánh khác.
    illicit_prob: float
    predicted_label: str  # 'illicit' | 'licit'
    #: Nhãn công khai Elliptic (không bịa) — để đối chiếu, không phải căn cứ.
    true_label: str | None = None
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL
    requires_review: bool
    headline: str
    reasons: list[str] = Field(default_factory=list)
    caveat: str
    # Quy kết theo TỪNG giao dịch (Saabas): đặc trưng nào đẩy điểm của chính nó.
    drivers: list[BitcoinDriverOut] = Field(default_factory=list)
    #: Phần lực đẩy "nghi ngờ" đến từ đặc trưng ĐỌC ĐƯỢC (còn lại là ẩn danh).
    meaningful_push_share: float | None = None
    #: Tỷ phần |SHAP| đến từ đặc trưng CÓ NGHĨA — "phần giải thích được của model",
    #: KHÔNG phải xác suất/nguyên nhân. Dùng cho thanh "Share of model explanation".
    interpretable_ratio: float | None = None
    #: CHẤT LƯỢNG GIẢI THÍCH (HIGH/MEDIUM/LIMITED) — TÁCH khỏi điểm rủi ro.
    explanation_quality: str | None = None
    # Bằng chứng đồ thị THẬT (txs_edgelist). NGỮ CẢNH cho chuyên viên — model
    # KHÔNG dùng đồ thị để chấm; điểm số hoàn toàn từ đặc trưng.
    graph_in_degree: int | None = None
    graph_out_degree: int | None = None
    #: MODEL DỰ ĐOÁN gắn cờ (khác known-illicit bên dưới).
    graph_flagged_neighbours: int | None = None
    #: GROUND TRUTH: số láng giềng có NHÃN THẬT bất hợp pháp.
    graph_known_illicit_neighbours: int | None = None
    graph_neighbours: list[BitcoinNeighbourOut] = Field(default_factory=list)
    # --- Interpretable Investigation Evidence Layer (tính SAU suy luận) -------
    #: NONE/WEAK/MODERATE/STRONG — sức mạnh bằng chứng ĐIỀU TRA, TÁCH khỏi rủi ro model.
    evidence_strength: str | None = None
    #: Object bằng chứng đồ thị có cấu trúc (multi-hop, hop-distance, topology…).
    graph_evidence: dict[str, Any] = Field(default_factory=dict)
    #: Lý do tất định kèm badge nguồn (ưu tiên bằng chứng mạnh trước tín hiệu ẩn danh).
    evidence_reasons: list[EvidenceReasonOut] = Field(default_factory=list)
    #: Gợi ý điều tra sinh từ bằng chứng thật.
    recommended_steps: list[str] = Field(default_factory=list)
    #: RiskReason hợp nhất (deterministic): SHAP + ngữ nghĩa + percentile + temporal + side.
    risk_reasons: list[RiskReasonOut] = Field(default_factory=list)


class BitcoinSummaryOut(BaseModel):
    release_id: str
    model_version: str
    region_label: str = "Giao dịch Bitcoin"
    #: Toàn tập test đã chấm.
    total_scored: int
    #: Số giao dịch MODEL gắn cờ bất hợp pháp (predicted illicit).
    flagged_illicit: int
    #: Trong nhóm gắn cờ, bao nhiêu ở mức HIGH/CRITICAL (cần rà soát).
    requires_review: int
    #: Đếm theo mức rủi ro trên toàn tập.
    by_level: dict[str, int] = Field(default_factory=dict)
    #: Số giao dịch THẬT là bất hợp pháp trong tập test (nhãn Elliptic).
    illicit_true_total: int
    #: Trong nhóm gắn cờ, bao nhiêu trùng nhãn thật (dự đoán đúng).
    flagged_true_positive: int
    #: Chỉ số đã ký của release (tập test) — cùng nguồn với trang Đánh giá chuẩn.
    f1: float | None = None
    precision: float | None = None
    recall: float | None = None
    pr_auc: float | None = None
    test_timestep_min: int | None = None
    test_timestep_max: int | None = None


class BitcoinPageOut(BaseModel):
    summary: BitcoinSummaryOut
    rows: list[BitcoinScoredRowOut]
    #: Số dòng khớp bộ lọc hiện tại (để phân trang).
    total: int
    page: int
    page_size: int
