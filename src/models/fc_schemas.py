"""Hợp đồng dữ liệu cho các màn hình "Thành phố tài chính".

Tách khỏi `schemas.py` vì hai nhóm phục vụ hai thứ khác nhau: `schemas.py` là
quy trình AML đang vận hành (cảnh báo, vụ việc, SAR, phê duyệt), còn file này
là dữ liệu do mô phỏng ABM sinh ra theo tài liệu thiết kế v2.0.

Quy ước chung với phần còn lại của API: NUMERIC của PostgreSQL đi qua JSON
dưới dạng chuỗi, nên các trường tiền tệ khai báo là `float` và được ép kiểu ở
tầng truy vấn, chứ không để Decimal rơi ra ngoài.
"""

from datetime import datetime
from typing import Literal

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
    data_mode: Literal["operational", "simulation"]
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
    amount_usd: float
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


class SearchHitOut(BaseModel):
    id: str
    label: str
    kind: str
    href: str


class TxRowOut(BaseModel):
    id: int
    occurred_at: datetime
    from_account: str
    to_account: str
    amount: float
    currency: str
    channel: str
    remarks: str
    # Nhãn rửa tiền chỉ đi kèm khi người gọi có quyền kiểm định; mặc định None.
    is_laundering: bool | None = None


class TxPageOut(BaseModel):
    rows: list[TxRowOut]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = ConfigDict(populate_by_name=True)
