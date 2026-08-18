from __future__ import annotations

import json
import math
import statistics
import time
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import (
    AnomalousFeature,
    AnomalyExplanationResult,
    BehaviorResult,
    EvidenceEnvelope,
    EvidenceType,
    GraphEdge,
    GraphEvidenceResult,
    GraphNeighborhoodResult,
    ObservedActivity,
    RiskBreakdown,
    RiskComponent,
    TransactionPage,
    TransactionRecord,
    TypologyAssignment,
    TypologyResult,
)
from src.observability.metrics import METRICS, attrs

WINDOW_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


class RiskArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)


class BehaviorArgs(BaseModel):
    account_key: str = Field(min_length=3, max_length=128)
    window: Literal["1d", "7d", "30d", "90d"] = "7d"


class TransactionArgs(BaseModel):
    account_key: str | None = Field(default=None, max_length=128)
    counterparty: str | None = Field(default=None, max_length=128)
    transaction_ids: list[str] = Field(default_factory=list, max_length=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    direction: Literal["in", "out"] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None


class GraphEvidenceArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)
    pattern: str | None = Field(default=None, max_length=64)


class NeighborhoodArgs(BaseModel):
    account_key: str = Field(min_length=3, max_length=128)
    hops: int = Field(default=1, ge=1, le=4)
    time_window: Literal["1d", "7d", "30d", "90d"] = "7d"


class TypologyArgs(BaseModel):
    pattern: str | None = Field(default=None, max_length=64)
    typology_code: str | None = Field(default=None, pattern=r"^T(0[1-9]|10)$")


class AnomalyArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)
    account_key: str = Field(min_length=3, max_length=128)
    window: Literal["1d", "7d", "30d", "90d"] = "7d"


@dataclass
class ToolExecution:
    result: dict[str, Any]
    evidence: EvidenceEnvelope | None
    status: Literal["SUCCEEDED", "PARTIAL"] = "SUCCEEDED"


def _percentile(values: list[float], value: float) -> float:
    if not values:
        return 50.0
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    return round(100 * (below + 0.5 * equal) / len(values), 2)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _dwell_hours(
    incoming: list[tuple[datetime, str, str, float]],
    outgoing: list[tuple[datetime, str, str, float]],
) -> list[float]:
    """Khoảng thời gian tiền nằm lại: mỗi lần nhận tới lần chuyển đi kế tiếp.

    Tìm bằng tìm kiếm nhị phân chứ không quét tuyến tính. ``outgoing`` đã được
    sắp theo thời gian từ ``events.sort()``, nên "phần tử đầu tiên >= mốc nhận"
    chính là ``bisect_left`` — cùng một kết quả, nhưng O(n log n) thay vì O(n²).

    Bậc hai ở đây không phải chuyện lý thuyết: ``GetAnomalyExplanation`` tính
    đặc trưng cho 500 tài khoản tham chiếu, và chỉ cần một tài khoản trung
    chuyển lớn là tích incoming × outgoing lên tới hàng trăm triệu phép so sánh.
    Trên môi trường thật, worker chiếm 389% CPU và phiên điều tra không bao giờ
    kết thúc.
    """
    outgoing_times = [event[0] for event in outgoing]
    dwell: list[float] = []
    for incoming_time, *_ in incoming:
        index = bisect_left(outgoing_times, incoming_time)
        if index < len(outgoing_times):
            dwell.append((outgoing_times[index] - incoming_time).total_seconds() / 3600)
    return dwell


def _either_direction(param: str) -> str:
    """Điều kiện "tài khoản này ở một trong hai đầu giao dịch", dạng đi được chỉ mục.

    Viết thẳng ``(from_account_key = :x OR to_account_key = :x)`` thì PostgreSQL
    bỏ cả hai chỉ mục ``(account, occurred_at DESC)`` và quét tuần tự 6,1 triệu
    dòng. Dựng sẵn tập ``transaction_id`` bằng hai lần dò chỉ mục rồi lọc theo
    tập ấy cho **đúng cùng một tập kết quả**, nhưng chỉ chạm vài chục dòng.

    Mốc thời gian ``:snapshot`` được lặp lại trong truy vấn con là có chủ đích:
    thiếu nó, tập ứng viên phình ra toàn bộ lịch sử của tài khoản.
    """
    return f"""transaction_id IN (
        SELECT transaction_id FROM transaction
         WHERE from_account_key = :{param} AND occurred_at <= :snapshot
        UNION
        SELECT transaction_id FROM transaction
         WHERE to_account_key = :{param} AND occurred_at <= :snapshot
    )"""


def _recent_either_direction(param: str) -> str:
    """Như ``_either_direction`` nhưng chặn tập ứng viên ở N giao dịch gần nhất.

    ``_either_direction`` dựng đủ *mọi* mã giao dịch của tài khoản. Với tài khoản
    trung chuyển 223.590 giao dịch, câu ngoài phải nạp và sắp từng ấy dòng rồi
    mới cắt lấy 50 — trên Cloud SQL mất **hơn bảy phút** cho một lượt gọi công cụ.

    Câu ngoài sắp theo ``occurred_at DESC, transaction_id DESC``. Lấy N dòng mới
    nhất của mỗi chiều rồi hợp lại và lấy N dòng mới nhất của phần hợp ấy cho
    **đúng** N giao dịch mới nhất của tài khoản — tức là đã chứa trọn những gì
    LIMIT/OFFSET bên ngoài có thể trả về. Không mất dòng nào, miễn là không còn
    bộ lọc nào khác thu hẹp kết quả (xem chỗ gọi).
    """
    branch = """
        (SELECT transaction_id, occurred_at FROM transaction
          WHERE {side} = :{param} AND occurred_at <= :snapshot
          ORDER BY occurred_at DESC, transaction_id DESC
          LIMIT :candidates)
    """
    return f"""transaction_id IN (
        SELECT transaction_id FROM (
            {branch.format(side="from_account_key", param=param)}
            UNION ALL
            {branch.format(side="to_account_key", param=param)}
        ) gan_nhat
         ORDER BY occurred_at DESC, transaction_id DESC
         LIMIT :candidates
    )"""


def _observed_from_rows(
    account_key: str,
    rows: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    window_days: int,
) -> ObservedActivity:
    """Same window as the feature vector, kept in original units."""
    events: list[tuple[datetime, str, str, float]] = []
    for row in rows:
        direction = "out" if row["from_account_key"] == account_key else "in"
        counterparty = row["to_account_key"] if direction == "out" else row["from_account_key"]
        events.append((row["occurred_at"], direction, counterparty, float(row["amount"])))
    events.sort()
    incoming = [event for event in events if event[1] == "in"]
    outgoing = [event for event in events if event[1] == "out"]
    total_out = sum(event[3] for event in outgoing)

    rapid_amount = 0.0
    prior_incoming: datetime | None = None
    for timestamp, direction, _counterparty, amount in events:
        if direction == "in":
            prior_incoming = timestamp
        elif prior_incoming and timestamp - prior_incoming <= timedelta(hours=2):
            rapid_amount += amount

    dwell_hours = _dwell_hours(incoming, outgoing)

    historical_counterparties: set[str] = set()
    for row in history:
        if row["from_account_key"] == account_key:
            historical_counterparties.add(row["to_account_key"])
        else:
            historical_counterparties.add(row["from_account_key"])
    current_counterparties = {event[2] for event in events}

    currencies = {row["currency"] for row in rows if row.get("currency")}
    return ObservedActivity(
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        currency=currencies.pop() if len(currencies) == 1 else None,
        inflow_amount=round(sum(event[3] for event in incoming), 2),
        outflow_amount=round(total_out, 2),
        largest_amount=round(max((event[3] for event in events), default=0.0), 2),
        incoming_count=len(incoming),
        outgoing_count=len(outgoing),
        unique_in_counterparties=len({event[2] for event in incoming}),
        unique_out_counterparties=len({event[2] for event in outgoing}),
        new_counterparties=len(current_counterparties - historical_counterparties),
        rapid_outflow_amount=round(rapid_amount, 2),
        rapid_outflow_percent=round(100 * rapid_amount / total_out, 2) if total_out > 0 else 0.0,
        median_dwell_hours=round(statistics.median(dwell_hours), 2) if dwell_hours else None,
        active_days=len({event[0].date() for event in events}),
    )


def _behavior_from_rows(
    account_key: str, rows: list[dict[str, Any]], history: list[dict[str, Any]]
) -> dict[str, float | int]:
    events: list[tuple[datetime, str, str, float]] = []
    for row in rows:
        direction = "out" if row["from_account_key"] == account_key else "in"
        counterparty = row["to_account_key"] if direction == "out" else row["from_account_key"]
        events.append((row["occurred_at"], direction, counterparty, float(row["amount"])))
    events.sort()
    incoming = [event for event in events if event[1] == "in"]
    outgoing = [event for event in events if event[1] == "out"]
    amounts = [event[3] for event in events]
    total_in = sum(event[3] for event in incoming)
    total_out = sum(event[3] for event in outgoing)
    active_days = len({event[0].date() for event in events})

    rapid_amount = 0.0
    prior_incoming: datetime | None = None
    for timestamp, direction, _counterparty, amount in events:
        if direction == "in":
            prior_incoming = timestamp
        elif prior_incoming and timestamp - prior_incoming <= timedelta(hours=2):
            rapid_amount += amount

    dwell_hours = _dwell_hours(incoming, outgoing)

    historical_counterparties: set[str] = set()
    for row in history:
        if row["from_account_key"] == account_key:
            historical_counterparties.add(row["to_account_key"])
        else:
            historical_counterparties.add(row["from_account_key"])
    current_counterparties = {event[2] for event in events}
    new_ratio = (
        len(current_counterparties - historical_counterparties) / len(current_counterparties)
        if current_counterparties
        else 0.0
    )

    # Đếm một lần rồi tra bảng, thay vì amounts.count() *bên trong* vòng lặp qua
    # chính amounts. Cách cũ là O(n²): với tài khoản trung chuyển 148.164 giao
    # dịch trong cửa sổ, đó là khoảng 2,2 x 10^10 phép so sánh — đo được 353
    # giây cho một lượt gọi công cụ, và phiên điều tra không bao giờ kết thúc.
    # Kết quả không đổi: vẫn là tỷ lệ giao dịch có số tiền trùng với ít nhất một
    # giao dịch khác.
    amount_counts = Counter(amounts)
    repeated = sum(amount_counts[value] >= 2 for value in amounts) / len(amounts) if amounts else 0.0
    gaps = [(events[i][0] - events[i - 1][0]).total_seconds() / 60 for i in range(1, len(events))]
    std = statistics.stdev(amounts) if len(amounts) > 1 else 0.0
    return {
        "txn_count": len(events),
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
        "active_days": active_days,
        "txn_per_active_day": round(len(events) / max(active_days, 1), 6),
        "total_inflow": round(math.log1p(total_in), 6),
        "total_outflow": round(math.log1p(total_out), 6),
        "net_flow": round(math.copysign(math.log1p(abs(total_in - total_out)), total_in - total_out), 6),
        "outflow_inflow_ratio": round(total_out / max(total_in, 1e-6), 6),
        "rapid_outflow_ratio": round(rapid_amount / max(total_out, 1e-6), 6),
        "median_dwell_time": round(statistics.median(dwell_hours), 6) if dwell_hours else 999.0,
        "unique_in_counterparties": len({event[2] for event in incoming}),
        "unique_out_counterparties": len({event[2] for event in outgoing}),
        "new_counterparty_ratio": round(new_ratio, 6),
        "median_amount": round(math.log1p(statistics.median(amounts)), 6) if amounts else 0.0,
        "p90_amount": round(math.log1p(_quantile(amounts, 0.9)), 6) if amounts else 0.0,
        "amount_std": round(math.log1p(std), 6),
        "repeated_amount_ratio": round(repeated, 6),
        "median_inter_txn_gap": round(statistics.median(gaps), 6) if gaps else 99999.0,
        "p10_inter_txn_gap": round(_quantile(gaps, 0.1), 6) if gaps else 99999.0,
    }


class InvestigationTools:
    """Allow-listed deterministic tool gateway.

    All traversal and calculations happen here. Agent outputs can select a
    tool and bounded arguments, but cannot issue SQL or execute arbitrary code.
    """

    ALLOWED = {
        "GetRiskBreakdown",
        "GetAccountBehavior",
        "GetTransactions",
        "GetGraphEvidence",
        "GetGraphNeighborhood",
        "GetTypology",
        "GetAnomalyExplanation",
    }
    ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
        "GetRiskBreakdown": RiskArgs,
        "GetAccountBehavior": BehaviorArgs,
        "GetTransactions": TransactionArgs,
        "GetGraphEvidence": GraphEvidenceArgs,
        "GetGraphNeighborhood": NeighborhoodArgs,
        "GetTypology": TypologyArgs,
        "GetAnomalyExplanation": AnomalyArgs,
    }
    DESCRIPTIONS = {
        "GetRiskBreakdown": "Retrieve the authoritative detector risk score and available branch contributions.",
        "GetAccountBehavior": "Retrieve deterministic account behavior features for a bounded time window.",
        "GetTransactions": "Retrieve bounded source transactions involving the investigation account.",
        "GetGraphEvidence": "Retrieve structured evidence emitted by the graph detector for this alert.",
        "GetGraphNeighborhood": "Traverse a bounded transaction neighborhood deterministically.",
        "GetTypology": "Resolve a typology through the versioned structured catalog.",
        "GetAnomalyExplanation": "Retrieve deterministic feature-deviation attribution for an ML alert.",
    }

    def __init__(self, session: Session, repository: InvestigationRepository, investigation_id: str):
        self.session = session
        self.repository = repository
        self.investigation_id = investigation_id
        self.state = repository.get(investigation_id)
        self.settings = get_settings()

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecution:
        if tool_name not in self.ALLOWED:
            self._reject_tool(tool_name, "Tool name is outside the allow-listed registry")
            raise ValueError(f"Công cụ {tool_name!r} không nằm trong danh sách được phép")
        try:
            validated = self.ARGUMENT_MODELS[tool_name].model_validate(self._bind_identity(tool_name, arguments))
            self._authorize(tool_name, validated)
        except Exception as exc:
            self._reject_tool(tool_name, type(exc).__name__)
            raise
        methods = {
            "GetRiskBreakdown": self.get_risk_breakdown,
            "GetAccountBehavior": self.get_account_behavior,
            "GetTransactions": self.get_transactions,
            "GetGraphEvidence": self.get_graph_evidence,
            "GetGraphNeighborhood": self.get_graph_neighborhood,
            "GetTypology": self.get_typology,
            "GetAnomalyExplanation": self.get_anomaly_explanation,
        }
        return methods[tool_name](validated.model_dump(mode="json", exclude_none=True))

    @classmethod
    def tool_catalog(cls) -> list[dict[str, Any]]:
        """Gemini-visible JSON schemas; execution remains backend-controlled."""
        return [
            {
                "name": name,
                "description": cls.DESCRIPTIONS[name],
                "parameters": cls.ARGUMENT_MODELS[name].model_json_schema(),
            }
            for name in sorted(cls.ALLOWED)
        ]

    def _reject_tool(self, tool_name: str, reason: str) -> None:
        event_type = "unauthorized_tool_request" if reason == "PermissionError" else "invalid_tool_request"
        METRICS.security_events.add(1, attrs(type=event_type))
        self.repository.add_trace(
            self.investigation_id,
            agent="investigation_supervisor",
            event_type="INVALID_TOOL_REQUEST",
            tool=tool_name[:128],
            rationale=f"Rejected Gemini tool request: {reason}.",
        )

    def _bind_identity(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Supply the subject the investigation is already pinned to.

        A model that asks for the right tool but forgets ``alert_id`` used to
        lose the whole call to a ValidationError. Filling these two fields in
        cannot widen access: ``_authorize`` rejects any value other than this
        investigation's own, so the only reachable value is the one bound here.
        Keys the tool does not declare are dropped rather than rejected.
        """
        fields = self.ARGUMENT_MODELS[tool_name].model_fields
        bound = {key: value for key, value in arguments.items() if key in fields}
        if "alert_id" in fields and not bound.get("alert_id"):
            bound["alert_id"] = self.state.alert_id
        if "account_key" in fields and not bound.get("account_key"):
            bound["account_key"] = self.state.account_key
        return bound

    def _authorize(self, tool_name: str, arguments: BaseModel) -> None:
        """Confine model-proposed arguments to the current investigation."""
        values = arguments.model_dump()
        if "alert_id" in values and values["alert_id"] != self.state.alert_id:
            raise PermissionError("Tool alert_id is outside the current investigation")
        if (
            tool_name
            in {
                "GetAccountBehavior",
                "GetTransactions",
                "GetGraphNeighborhood",
                "GetAnomalyExplanation",
            }
            and values.get("account_key") != self.state.account_key
        ):
            raise PermissionError("Tool account_key is outside the current investigation")

    #: Khoá bắt buộc trong ``behavior_feature_snapshot.features`` để coi là ảnh
    #: chụp có hợp nhất điểm. Thiếu bất kỳ khoá nào thì coi như không có.
    _FUSION_KEYS = (
        "isolation_forest_percentile",
        "graph_percentile",
        "isolation_forest_contribution",
        "graph_contribution",
        "champion",
    )

    def _fusion_snapshot(self, account_key: str, as_of_time: Any) -> dict[str, Any] | None:
        """Ảnh chụp đặc trưng đã hợp nhất điểm cho đúng tài khoản và mốc thời gian.

        ``scripts/load_fusion_release.py`` ghi phân vị và mức đóng góp của từng
        nhánh vào ``behavior_feature_snapshot.features``, với ``as_of_time``
        chính là ``created_at`` của cảnh báo sinh ra từ nó. Đây là chỗ duy nhất
        cần đọc — không suy diễn, không tính lại điểm.
        """
        row = (
            self.session.execute(
                text(
                    """SELECT snapshot_id, model_version, features
                         FROM behavior_feature_snapshot
                        WHERE account_key = :account AND as_of_time = :as_of
                        ORDER BY created_at DESC
                        LIMIT 1"""
                ),
                {"account": account_key, "as_of": as_of_time},
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        features = row["features"] or {}
        if any(key not in features for key in self._FUSION_KEYS):
            return None
        return {"snapshot_id": row["snapshot_id"], "model_version": row["model_version"], **features}

    @staticmethod
    def _branch(percentile: Any, contribution: Any, source_ref: str) -> RiskComponent:
        """Một nhánh detector trong bản hợp nhất.

        Trọng số suy ngược từ ``contribution = weight × percentile`` (xem
        ``src/fusion/model.py``). Phân vị bằng 0 thì trọng số không xác định —
        báo 0 chứ không chia cho 0.

        ``available`` giữ đúng nghĩa mà tác tử phản biện đang dựa vào: *nhánh
        này có góp vào điểm cuối cùng hay không*. Biết phân vị nhưng trọng số
        bằng 0 thì vẫn là không góp — nếu báo available ở đây, bộ phản biện sẽ
        đòi bằng chứng đồ thị cho một nhánh chưa hề tham gia.
        """
        pct = float(percentile) if percentile is not None else 0.0
        contrib = float(contribution) if contribution is not None else 0.0
        if not math.isfinite(pct) or not math.isfinite(contrib):
            pct, contrib = 0.0, 0.0
        weight = contrib / pct if pct > 0 else 0.0
        return RiskComponent(
            score=round(min(max(pct, 0.0), 1.0), 6),
            weight=round(min(max(weight, 0.0), 1.0), 6),
            contribution=round(min(max(contrib, 0.0), 1.0), 6),
            available=weight > 0,
            source_ref=source_ref if weight > 0 else None,
        )

    def _risk_components(
        self,
        *,
        alert_id: str,
        account_key: str,
        detector: str,
        score: float,
        as_of_time: Any,
    ) -> tuple[dict[str, RiskComponent], bool, str | None]:
        """Phân rã điểm rủi ro theo đúng những gì dữ liệu có.

        Hai đường:

        * Có bản phát hành hợp nhất cho cảnh báo này → đọc phân vị và mức đóng
          góp thật của từng nhánh.
        * Không có → điểm của bộ phát hiện là điểm cuối cùng, các nhánh còn lại
          báo *không khả dụng* chứ không suy đoán giá trị.

        Điểm cuối cùng luôn lấy từ bảng ``alert`` ở cả hai đường: công cụ này
        giải thích điểm, không được phép tính lại điểm.
        """
        snapshot = self._fusion_snapshot(account_key, as_of_time)
        if snapshot is not None:
            champion = str(snapshot.get("champion", ""))
            source_ref = f"behavior_feature_snapshot:{snapshot['snapshot_id']}"
            if champion == "fusion":
                # Nhánh rule chỉ có mặt trong bản hợp nhất ba nhánh; bản hai nhánh
                # cũ không ghi hai khoá này và nhánh rule đúng là không tham gia.
                has_rule = "rule_percentile" in snapshot and "rule_contribution" in snapshot
                components = {
                    "rule": (
                        self._branch(snapshot["rule_percentile"], snapshot["rule_contribution"], source_ref)
                        if has_rule
                        else RiskComponent(score=0, weight=0, contribution=0, available=False)
                    ),
                    "anomaly": self._branch(
                        snapshot["isolation_forest_percentile"],
                        snapshot["isolation_forest_contribution"],
                        source_ref,
                    ),
                    "graph": self._branch(snapshot["graph_percentile"], snapshot["graph_contribution"], source_ref),
                }
                branches = ", ".join(name for name, c in components.items() if c.available) or "none"
                return (
                    components,
                    True,
                    (
                        f"Final score is the weighted fusion of the {branches} branch(es) recorded in "
                        f"{source_ref} (fusion model {snapshot['model_version']}). A branch with zero weight "
                        "was evaluated and selected out on validation, not omitted."
                    ),
                )
            # Bản phát hành có chạy hợp nhất nhưng một nhánh đơn thắng ở bước
            # kiểm định, nên điểm cuối cùng là điểm của nhánh đó. Nói thẳng tên
            # nhánh thắng thay vì báo "không có hợp nhất".
            winner = {"isolation_forest": "anomaly", "graph": "graph"}.get(champion, "anomaly")
            components = {
                name: RiskComponent(
                    score=score if name == winner else 0,
                    weight=1 if name == winner else 0,
                    contribution=score if name == winner else 0,
                    available=name == winner,
                    source_ref=f"alert:{alert_id}" if name == winner else None,
                )
                for name in ("rule", "anomaly", "graph")
            }
            return (
                components,
                False,
                (
                    f"Fusion was evaluated for this release but the single '{champion}' detector was selected "
                    f"as champion on validation, so its score is the authoritative final score. Recorded in "
                    f"{source_ref}."
                ),
            )

        # Tên nhánh trong bảng phân rã, theo bộ phát hiện đã mở cảnh báo.
        #
        # `.get` chứ không tra cứng: bảng cũ chỉ có ba khoá và ném KeyError ngay
        # khi gặp `mega_pna`, làm hỏng CẢ phiên điều tra chứ không chỉ một công
        # cụ. Một nhánh mới không được phép đánh sập cả quy trình — chưa biết thì
        # ghi là chưa biết.
        source = {"rule": "rule", "ml": "anomaly", "graph": "graph", "mega_pna": "mega_pna"}.get(detector)
        branches = ("rule", "anomaly", "graph", "mega_pna")
        components = {
            name: RiskComponent(
                score=score if name == source else 0,
                weight=1 if name == source else 0,
                contribution=score if name == source else 0,
                available=name == source,
                source_ref=f"alert:{alert_id}" if name == source else None,
            )
            for name in branches
        }
        if source is None:
            return (
                components,
                False,
                f"Bộ phát hiện '{detector}' chưa có tên nhánh trong bảng phân rã; "
                f"điểm cuối cùng vẫn lấy từ bảng alert.",
            )
        return (
            components,
            False,
            (
                "Không có bản hợp nhất điểm nào phủ cảnh báo này; điểm của bộ phát hiện là điểm cuối cùng "
                "chính thức. Các nhánh còn lại là không có dữ liệu, không phải được suy đoán bằng 0."
            ),
        )

    def get_risk_breakdown(self, raw: dict[str, Any]) -> ToolExecution:
        args = RiskArgs.model_validate(raw)
        row = (
            self.session.execute(
                text("SELECT alert_id, account_key, detector, risk_score, created_at FROM alert WHERE alert_id = :id"),
                {"id": args.alert_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise LookupError(f"Không tìm thấy cảnh báo {args.alert_id}")
        score = round(float(row["risk_score"]) / 100, 6)
        components, fusion_available, limitation = self._risk_components(
            alert_id=args.alert_id,
            account_key=row["account_key"],
            detector=row["detector"],
            score=score,
            as_of_time=row["created_at"],
        )
        result = RiskBreakdown(
            alert_id=args.alert_id,
            final_risk_score=score,
            fusion_available=fusion_available,
            components=components,
            limitation=limitation,
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.RISK_BREAKDOWN,
            source="detection_engine",
            account_key=row["account_key"],
            payload=result.model_dump(mode="json"),
            source_record_ids=[args.alert_id],
        )
        if row["detector"] == "rule":
            reasons = [
                dict(reason)
                for reason in self.session.execute(
                    text(
                        """SELECT factor_code, factor_label, contribution, weight
                             FROM alert_reason WHERE alert_id = :id ORDER BY contribution DESC"""
                    ),
                    {"id": args.alert_id},
                ).mappings()
            ]
            self.repository.add_evidence(
                self.investigation_id,
                evidence_type=EvidenceType.RULE_TRIGGER,
                source="rule_engine",
                account_key=row["account_key"],
                payload={"alert_id": args.alert_id, "triggered_rules": reasons},
                source_record_ids=[args.alert_id, *[reason["factor_code"] for reason in reasons]],
            )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    #: Lấy giao dịch của **nhiều** tài khoản trong một lượt.
    #:
    #: Nối hai lần theo hai chỉ mục ``(account, occurred_at DESC)`` rồi UNION,
    #: thay vì một mệnh đề OR — dấu OR khiến PostgreSQL không dùng được chỉ mục
    #: nào trong hai. Cột ``owner`` cho biết dòng này thuộc về tài khoản tham
    #: chiếu nào; một giao dịch nối hai tài khoản trong mẫu sẽ xuất hiện hai
    #: lần, mỗi lần dưới một chủ sở hữu, đúng như khi hỏi riêng từng tài khoản.
    _BATCH_WINDOW_SQL = """
        WITH acct AS (SELECT unnest(CAST(:accounts AS text[])) AS account_key)
        SELECT a.account_key AS owner, t.transaction_id, t.occurred_at,
               t.from_account_key, t.to_account_key, t.amount, t.currency
          FROM acct a
          JOIN transaction t ON t.from_account_key = a.account_key
         WHERE t.occurred_at > :start AND t.occurred_at <= :as_of
        UNION
        SELECT a.account_key AS owner, t.transaction_id, t.occurred_at,
               t.from_account_key, t.to_account_key, t.amount, t.currency
          FROM acct a
          JOIN transaction t ON t.to_account_key = a.account_key
         WHERE t.occurred_at > :start AND t.occurred_at <= :as_of
    """

    _BATCH_HISTORY_SQL = """
        WITH acct AS (SELECT unnest(CAST(:accounts AS text[])) AS account_key)
        SELECT a.account_key AS owner, t.transaction_id, t.occurred_at,
               t.from_account_key, t.to_account_key, t.amount
          FROM acct a
          JOIN transaction t ON t.from_account_key = a.account_key
         WHERE t.occurred_at <= :start
        UNION
        SELECT a.account_key AS owner, t.transaction_id, t.occurred_at,
               t.from_account_key, t.to_account_key, t.amount
          FROM acct a
          JOIN transaction t ON t.to_account_key = a.account_key
         WHERE t.occurred_at <= :start
    """

    def _reference_features(self, accounts: list[str], window: str) -> dict[str, dict[str, float | int]]:
        """Đặc trưng hành vi của cả mẫu tham chiếu, bằng đúng hai truy vấn.

        Bản trước gọi ``_behavior`` trong vòng lặp qua 500 tài khoản — 1.500
        truy vấn cho **một** lần gọi công cụ. Trên máy chạy thử thì không ai
        để ý; trên Cloud SQL, mỗi truy vấn mất vài giây vì đĩa chậm, và một
        phiên điều tra kéo dài **44 phút**, trong đó 43 phút nằm ở riêng chỗ này.
        Người dùng bấm "Điều tra" rồi không bao giờ thấy kết quả.

        Phép tính không đổi: vẫn ``_behavior_from_rows`` trên đúng những dòng ấy,
        chỉ khác là gom về theo tài khoản ở Python thay vì hỏi lại cơ sở dữ liệu
        từng lần. Tài khoản không có giao dịch nào vẫn có mặt với danh sách rỗng,
        y như khi hỏi riêng — bỏ nó đi sẽ làm lệch phân vị.
        """
        if not accounts:
            return {}
        as_of = self.state.snapshot_time
        start = as_of - timedelta(days=WINDOW_DAYS[window])
        params = {"accounts": accounts, "start": start, "as_of": as_of}

        rows_by_account: dict[str, list[dict[str, Any]]] = {account: [] for account in accounts}
        for row in self.session.execute(text(self._BATCH_WINDOW_SQL), params).mappings():
            rows_by_account[row["owner"]].append(dict(row))

        history_by_account: dict[str, list[dict[str, Any]]] = {account: [] for account in accounts}
        for row in self.session.execute(text(self._BATCH_HISTORY_SQL), params).mappings():
            history_by_account[row["owner"]].append(dict(row))

        return {
            account: _behavior_from_rows(account, rows_by_account[account], history_by_account[account])
            for account in accounts
        }

    #: Giao dịch của **một** tài khoản trong cửa sổ, và toàn bộ lịch sử trước đó.
    #:
    #: Cả hai từng viết ``WHERE ... AND (from_account_key = :account OR
    #: to_account_key = :account)``. Dấu OR ấy khiến PostgreSQL không dùng được
    #: cả hai chỉ mục ``(account, occurred_at DESC)`` và rơi xuống quét tuần tự
    #: 6,1 triệu dòng. Trên máy chạy thử thì vài trăm mili giây; trên Cloud SQL
    #: là **hơn tám phút cho một lượt gọi công cụ** — và ``GetAccountBehavior``
    #: là công cụ tác tử gọi gần như đầu tiên trong mọi phiên điều tra.
    #:
    #: Tách thành hai nhánh rồi UNION thì mỗi nhánh đi đúng một chỉ mục. Dùng
    #: UNION chứ không UNION ALL, và có ``transaction_id`` trong cả hai nhánh,
    #: để một giao dịch tự chuyển (nếu có) vẫn chỉ đếm một lần — đúng như mệnh
    #: đề OR cũ.
    _WINDOW_SQL = """
        (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency
           FROM transaction
          WHERE from_account_key = :account AND occurred_at > :start AND occurred_at <= :as_of)
        UNION
        (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency
           FROM transaction
          WHERE to_account_key = :account AND occurred_at > :start AND occurred_at <= :as_of)
        ORDER BY occurred_at, transaction_id
    """

    _HISTORY_SQL = """
        (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount
           FROM transaction
          WHERE from_account_key = :account AND occurred_at <= :start)
        UNION
        (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount
           FROM transaction
          WHERE to_account_key = :account AND occurred_at <= :start)
    """

    def _behavior(self, account_key: str, window: str) -> BehaviorResult:
        if not self.session.execute(
            text("SELECT EXISTS(SELECT 1 FROM account WHERE account_key = :account)"), {"account": account_key}
        ).scalar_one():
            raise LookupError(f"Không tìm thấy tài khoản {account_key}")
        as_of = self.state.snapshot_time
        start = as_of - timedelta(days=WINDOW_DAYS[window])
        rows = [
            dict(row)
            for row in self.session.execute(
                text(self._WINDOW_SQL),
                {"start": start, "as_of": as_of, "account": account_key},
            ).mappings()
        ]
        history = [
            dict(row)
            for row in self.session.execute(
                text(self._HISTORY_SQL),
                {"start": start, "account": account_key},
            ).mappings()
        ]
        return BehaviorResult(
            account_key=account_key,
            window=window,
            as_of_time=as_of,
            feature_definition_version="feature_spec_v1",
            features=_behavior_from_rows(account_key, rows, history),
            observed=_observed_from_rows(
                account_key, rows, history, window_start=start, window_end=as_of, window_days=WINDOW_DAYS[window]
            ),
        )

    def get_account_behavior(self, raw: dict[str, Any]) -> ToolExecution:
        args = BehaviorArgs.model_validate(raw)
        result = self._behavior(args.account_key, args.window)
        source_ref = f"features:{args.account_key}:{result.as_of_time.isoformat()}:{args.window}:feature_spec_v1"
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.BEHAVIOR_FEATURE,
            source="feature_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[source_ref],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    def get_transactions(self, raw: dict[str, Any]) -> ToolExecution:
        args = TransactionArgs.model_validate(raw)
        if not args.account_key and not args.transaction_ids:
            raise ValueError("GetTransactions yêu cầu account_key hoặc transaction_ids")
        limit = min(args.limit, self.settings.investigation_tx_limit)
        offset = int(args.cursor or "0")
        if offset < 0 or offset > 10_000:
            raise ValueError("Con trỏ phân trang giao dịch không hợp lệ")
        conditions = ["occurred_at <= :snapshot"]
        params: dict[str, Any] = {"snapshot": self.state.snapshot_time, "limit": limit + 1, "offset": offset}
        if args.transaction_ids:
            ids = [int(value) for value in args.transaction_ids]
            conditions.append("transaction_id = ANY(:transaction_ids)")
            params["transaction_ids"] = ids
        # Chỉ chặn trước tập ứng viên khi tài khoản là *bộ lọc duy nhất* chọn dòng.
        #
        # Khi có thêm điều kiện (đối tác, khoảng thời gian, danh sách mã), lớp lọc
        # bên ngoài còn loại bớt nữa, nên cắt sớm có thể trả về thiếu dòng so với
        # câu hỏi thật. Lúc đó chấp nhận tập ứng viên đầy đủ.
        only_account = bool(args.account_key) and not (
            args.transaction_ids or args.counterparty or args.start_time or args.end_time
        )
        if args.account_key:
            if args.direction == "in":
                conditions.append("to_account_key = :account")
            elif args.direction == "out":
                conditions.append("from_account_key = :account")
            elif only_account:
                conditions.append(_recent_either_direction("account"))
                # Lấy đúng số dòng trang hiện tại cần tới, không hơn.
                params["candidates"] = limit + offset + 1
            else:
                conditions.append(_either_direction("account"))
            params["account"] = args.account_key
        if args.counterparty:
            conditions.append(_either_direction("counterparty"))
            params["counterparty"] = args.counterparty
        if args.start_time:
            conditions.append("occurred_at >= :start_time")
            params["start_time"] = args.start_time
        if args.end_time:
            conditions.append("occurred_at <= :end_time")
            params["end_time"] = args.end_time
        rows = list(
            self.session.execute(
                text(
                    f"""SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                               amount, currency, channel
                          FROM transaction WHERE {" AND ".join(conditions)}
                         ORDER BY occurred_at DESC, transaction_id DESC
                         LIMIT :limit OFFSET :offset"""
                ),
                params,
            ).mappings()
        )
        truncated = len(rows) > limit
        rows = rows[:limit]
        records = [
            TransactionRecord(
                transaction_id=str(row["transaction_id"]),
                source=row["from_account_key"],
                destination=row["to_account_key"],
                timestamp=row["occurred_at"],
                amount=float(row["amount"]),
                currency=row["currency"],
                payment_format=row["channel"],
            )
            for row in rows
        ]
        page = TransactionPage(
            items=records,
            limit=limit,
            next_cursor=str(offset + limit) if truncated else None,
            truncated=truncated,
        )
        refs = [record.transaction_id for record in records]
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.TRANSACTION,
            source="transaction_service",
            account_key=args.account_key or self.state.account_key,
            payload=page.model_dump(mode="json"),
            source_record_ids=refs or ["empty-query-result"],
            transaction_refs=refs,
            untrusted=True,
        )
        return ToolExecution(result=page.model_dump(mode="json"), evidence=evidence)

    def _graph_evidence_rows(self) -> list[dict[str, Any]]:
        """Bằng chứng đồ thị dùng được cho phiên điều tra này.

        Hai nguồn, theo thứ tự:

        1. ``evidence`` của vụ việc — sổ bằng chứng bất biến, dành cho bộ phát
           hiện nào ghi thẳng vào đó khi vụ việc đã tồn tại.
        2. ``graph_detector_evidence`` — kho của bộ phát hiện chạy theo lô, khoá
           theo (tài khoản, mốc thời gian). Bộ phát hiện chạy trước khi có vụ
           việc nên không thể ghi vào nguồn 1.

        Trước đây chỉ có nguồn 1, và vì không bộ phát hiện nào ghi vào đó, công
        cụ luôn trả ``available: false`` — nhánh đồ thị trong sơ đồ kiến trúc
        thực tế chưa từng chạy lần nào.
        """
        rows = [
            dict(row)
            for row in self.session.execute(
                text(
                    """SELECT evidence_id, payload FROM evidence
                        WHERE case_id = :case_id AND source_table = 'graph_detector'
                        ORDER BY retrieved_at DESC"""
                ),
                {"case_id": self.state.case_id},
            ).mappings()
        ]
        if rows:
            return rows
        # Khoá theo mốc của CHÍNH cảnh báo, không phải ``snapshot_time`` của
        # phiên điều tra. Hai mốc này cố ý khác nhau: ``snapshot_time`` là giao
        # dịch gần nhất của tài khoản tại hoặc trước cảnh báo (neo dữ liệu),
        # còn bộ phát hiện chạy theo mốc cắt cửa sổ của nó. Trên LI-Small chúng
        # lệch nhau bảy ngày, và so khớp bằng ``snapshot_time`` không tìm thấy gì.
        #
        # Lấy mốc detector gần nhất *tại hoặc trước* cảnh báo, rồi trả về mọi
        # mẫu hình ở đúng mốc đó — không trộn bằng chứng của hai cửa sổ.
        return [
            dict(row)
            for row in self.session.execute(
                text(
                    """WITH alert_time AS (
                           SELECT created_at FROM alert WHERE alert_id = :alert
                       ),
                       latest AS (
                           SELECT max(g.as_of_time) AS as_of
                             FROM graph_detector_evidence g, alert_time a
                            WHERE g.account_key = :account AND g.as_of_time <= a.created_at
                       )
                       SELECT g.evidence_id, g.payload
                         FROM graph_detector_evidence g, latest
                        WHERE g.account_key = :account AND g.as_of_time = latest.as_of
                        ORDER BY g.created_at DESC"""
                ),
                {"account": self.state.account_key, "alert": self.state.alert_id},
            ).mappings()
        ]

    def get_graph_evidence(self, raw: dict[str, Any]) -> ToolExecution:
        args = GraphEvidenceArgs.model_validate(raw)
        rows = self._graph_evidence_rows()
        for row in rows:
            # ``available`` và ``evidence_id`` do tầng này quyết định, nên bỏ ra
            # khỏi payload trước khi dựng — nguồn nào lỡ lưu chúng cũng không
            # làm hỏng lời gọi.
            payload = {k: v for k, v in row["payload"].items() if k not in {"available", "evidence_id"}}
            if payload.get("pattern") and (not args.pattern or payload["pattern"] == args.pattern):
                result = GraphEvidenceResult(**payload, evidence_id=row["evidence_id"], available=True)
                transaction_refs = [edge.transaction_id for edge in result.edges]
                evidence = self.repository.add_evidence(
                    self.investigation_id,
                    evidence_type=EvidenceType.GRAPH_PATTERN,
                    source="graph_detector",
                    account_key=self.state.account_key,
                    payload=result.model_dump(mode="json", by_alias=True),
                    source_record_ids=[row["evidence_id"], *transaction_refs],
                    transaction_refs=transaction_refs,
                )
                return ToolExecution(result=result.model_dump(mode="json", by_alias=True), evidence=evidence)
        result = GraphEvidenceResult(
            available=False,
            missing_reason="No structured graph-detector evidence exists for this alert; no graph pattern may be claimed.",
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=None, status="PARTIAL")

    def get_graph_neighborhood(self, raw: dict[str, Any]) -> ToolExecution:
        args = NeighborhoodArgs.model_validate(raw)
        hops = min(args.hops, self.settings.max_graph_hops)
        start = self.state.snapshot_time - timedelta(days=WINDOW_DAYS[args.time_window])
        visited = {args.account_key}
        frontier = {args.account_key}
        edge_rows: dict[str, dict[str, Any]] = {}
        truncated = False
        for _ in range(hops):
            if not frontier:
                break
            rows = self.session.execute(
                # Cùng lý do như _WINDOW_SQL: tách OR thành hai nhánh đi chỉ mục.
                # Ở đây mỗi nhánh còn giới hạn riêng rồi mới hợp lại — nếu chỉ
                # đặt LIMIT ở ngoài, PostgreSQL vẫn phải dựng đủ cả hai nhánh.
                text(
                    """SELECT transaction_id, from_account_key, to_account_key
                         FROM (
                             (SELECT transaction_id, occurred_at, from_account_key, to_account_key
                                FROM transaction
                               WHERE from_account_key = ANY(:frontier)
                                 AND occurred_at > :start AND occurred_at <= :snapshot
                               ORDER BY occurred_at DESC, transaction_id DESC
                               LIMIT :edge_limit)
                             UNION
                             (SELECT transaction_id, occurred_at, from_account_key, to_account_key
                                FROM transaction
                               WHERE to_account_key = ANY(:frontier)
                                 AND occurred_at > :start AND occurred_at <= :snapshot
                               ORDER BY occurred_at DESC, transaction_id DESC
                               LIMIT :edge_limit)
                         ) hop
                        ORDER BY occurred_at DESC, transaction_id DESC
                        LIMIT :edge_limit"""
                ),
                {
                    "start": start,
                    "snapshot": self.state.snapshot_time,
                    "frontier": list(frontier),
                    "edge_limit": self.settings.max_graph_edges + 1,
                },
            ).mappings()
            next_frontier: set[str] = set()
            for row in rows:
                if len(edge_rows) >= self.settings.max_graph_edges:
                    truncated = True
                    break
                edge_rows[str(row["transaction_id"])] = dict(row)
                for account in (row["from_account_key"], row["to_account_key"]):
                    if account not in visited:
                        if len(visited) >= self.settings.max_graph_nodes:
                            truncated = True
                            continue
                        visited.add(account)
                        next_frontier.add(account)
            frontier = next_frontier
        edges = [
            GraphEdge.model_validate(
                {"from": row["from_account_key"], "to": row["to_account_key"], "transaction_id": tx_id}
            )
            for tx_id, row in edge_rows.items()
        ]
        result = GraphNeighborhoodResult(
            account_key=args.account_key,
            hops=hops,
            nodes=sorted(visited),
            edges=edges,
            truncated=truncated,
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.GRAPH_NEIGHBORHOOD,
            source="transaction_graph_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json", by_alias=True),
            source_record_ids=list(edge_rows) or [f"empty-neighborhood:{args.account_key}"],
            transaction_refs=list(edge_rows),
        )
        return ToolExecution(result=result.model_dump(mode="json", by_alias=True), evidence=evidence)

    @staticmethod
    def _catalog() -> list[dict[str, Any]]:
        path = Path(__file__).with_name("typologies.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def _typology_assignment(self, typology_code: str) -> TypologyAssignment | None:
        """Dấu vết ánh xạ nhóm hành vi của chính cảnh báo đang điều tra.

        Trả về None khi bản ghi không tồn tại hoặc nói về một mã khác: tác tử
        chỉ được nhận thông tin ánh xạ đúng cho nhóm hành vi mà nó đang hỏi.
        """
        row = (
            self.session.execute(
                text(
                    """SELECT typology_code, is_fallback, observed_signals,
                              matched_required, matched_supporting, rationale
                         FROM alert_typology_match WHERE alert_id = :alert"""
                ),
                {"alert": self.state.alert_id},
            )
            .mappings()
            .first()
        )
        if not row or row["typology_code"] != typology_code:
            return None
        return TypologyAssignment(
            typology_code=row["typology_code"],
            is_fallback=bool(row["is_fallback"]),
            observed_signals=list(row["observed_signals"] or []),
            matched_required=list(row["matched_required"] or []),
            matched_supporting=list(row["matched_supporting"] or []),
            rationale=str(row["rationale"] or ""),
        )

    def get_typology(self, raw: dict[str, Any]) -> ToolExecution:
        args = TypologyArgs.model_validate(raw)
        if not args.pattern and not args.typology_code:
            raise ValueError("GetTypology yêu cầu pattern hoặc typology_code")
        entry = next(
            (
                item
                for item in self._catalog()
                if (args.pattern and item["pattern"] == args.pattern)
                or (args.typology_code and item["typology_code"] == args.typology_code)
            ),
            None,
        )
        if not entry:
            raise LookupError("Không tìm thấy ánh xạ nhóm hành vi")
        result = TypologyResult(**entry, assignment=self._typology_assignment(entry["typology_code"]))
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.TYPOLOGY_MAPPING,
            source="typology_registry",
            account_key=self.state.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[f"{result.typology_code}:{result.version}"],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    def get_anomaly_explanation(self, raw: dict[str, Any]) -> ToolExecution:
        args = AnomalyArgs.model_validate(raw)
        alert = (
            self.session.execute(
                text(
                    """SELECT alert_id, risk_score FROM alert
                        WHERE account_key = :account AND detector = 'ml'
                          AND (alert_id = :alert_id OR case_id = :case_id)
                        ORDER BY (alert_id = :alert_id) DESC, created_at DESC LIMIT 1"""
                ),
                {"account": args.account_key, "alert_id": args.alert_id, "case_id": self.state.case_id},
            )
            .mappings()
            .first()
        )
        if not alert:
            result = AnomalyExplanationResult(
                account_key=args.account_key,
                anomaly_score=0,
                top_anomalous_features=[],
                method="unavailable",
                available=False,
                missing_reason="No Isolation Forest detector result exists for this alert/account.",
            )
            return ToolExecution(result=result.model_dump(mode="json"), evidence=None, status="PARTIAL")

        target = self._behavior(args.account_key, args.window)
        reason_codes = {
            str(code).lower()
            for code in self.session.execute(
                text("SELECT factor_code FROM alert_reason WHERE alert_id = :id"), {"id": alert["alert_id"]}
            ).scalars()
        }
        candidate_features = [name for name in target.features if name.lower() in reason_codes]
        if not candidate_features:
            candidate_features = list(target.features)

        # Deterministic reference distribution from accounts active in the
        # same point-in-time window. This explains deviations; it does not
        # alter or approximate the detector score.
        #
        # Duyệt bảng `account` theo khoá chính rồi hỏi "tài khoản này có giao
        # dịch trong cửa sổ không", thay vì gom DISTINCT trên toàn bộ giao dịch
        # của cửa sổ. Cách cũ buộc PostgreSQL đọc hết vài triệu dòng rồi mới cắt
        # 500 — trên Cloud SQL riêng câu ấy chạy **quá 10 phút**. Cách này dừng
        # ngay khi đủ 500, mỗi lần hỏi là một lần dò chỉ mục.
        #
        # Mẫu chọn ra **không đổi**: vẫn là 500 tài khoản đứng đầu theo thứ tự
        # khoá có giao dịch trong cửa sổ. Giữ nguyên là bắt buộc — đổi mẫu là đổi
        # phân vị, và những kết luận đã lưu sẽ không còn tái lập được.
        active_accounts = list(
            self.session.execute(
                text(
                    """SELECT a.account_key
                         FROM account a
                        WHERE EXISTS (SELECT 1 FROM transaction t
                                       WHERE t.from_account_key = a.account_key
                                         AND t.occurred_at > :start AND t.occurred_at <= :snapshot)
                           OR EXISTS (SELECT 1 FROM transaction t
                                       WHERE t.to_account_key = a.account_key
                                         AND t.occurred_at > :start AND t.occurred_at <= :snapshot)
                        ORDER BY a.account_key
                        LIMIT 500"""
                ),
                {
                    "start": self.state.snapshot_time - timedelta(days=WINDOW_DAYS[args.window]),
                    "snapshot": self.state.snapshot_time,
                },
            ).scalars()
        )
        reference_features = self._reference_features(active_accounts, args.window)
        reference: dict[str, list[float]] = defaultdict(list)
        for account in active_accounts:
            computed = reference_features[account]
            for feature in candidate_features:
                reference[feature].append(float(computed[feature]))
        ranked: list[AnomalousFeature] = []
        for feature in candidate_features:
            value = float(target.features[feature])
            percentile = _percentile(reference[feature], value)
            ranked.append(
                AnomalousFeature(
                    feature=feature,
                    value=value,
                    reference_percentile=percentile,
                    source_ref=f"feature:{args.account_key}:{feature}:{target.as_of_time.isoformat()}",
                )
            )
        ranked.sort(key=lambda item: abs(item.reference_percentile - 50), reverse=True)
        result = AnomalyExplanationResult(
            account_key=args.account_key,
            anomaly_score=round(float(alert["risk_score"]) / 100, 6),
            top_anomalous_features=ranked[:5],
            method="same-window empirical percentile; detector score unchanged",
            available=True,
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.ANOMALY_EXPLANATION,
            source="anomaly_explanation_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[alert["alert_id"], f"feature_spec_v1:{args.window}"],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)


def timed_execute(
    tools: InvestigationTools, tool_name: str, arguments: dict[str, Any]
) -> tuple[ToolExecution, datetime, int]:
    started_at = datetime.now(UTC)
    started = time.monotonic()
    result = tools.execute(tool_name, arguments)
    return result, started_at, round((time.monotonic() - started) * 1000)
