from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.llm import GeminiCallResult, GeminiService
from src.investigation.prompts import get_prompt
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import (
    Claim,
    EvidenceEnvelope,
    EvidenceType,
    Explanation,
    RiskDriver,
    SupervisorPlan,
    ToolDecision,
    ValidationIssue,
    ValidationResult,
)
from src.investigation.tools import InvestigationTools


def _claim_id() -> str:
    return f"CLM-{uuid.uuid4().hex[:16]}"


# Feature names stay verbatim in claim text for traceability; the gloss is what
# a reviewer actually reads.
FEATURE_LABELS_VI = {
    "txn_count": "số giao dịch",
    "incoming_count": "số giao dịch nhận",
    "outgoing_count": "số giao dịch chuyển đi",
    "active_days": "số ngày có phát sinh",
    "txn_per_active_day": "số giao dịch mỗi ngày hoạt động",
    "total_inflow": "tổng tiền vào",
    "total_outflow": "tổng tiền ra",
    "net_flow": "dòng tiền ròng",
    "outflow_inflow_ratio": "tỉ lệ tiền ra trên tiền vào",
    "rapid_outflow_ratio": "tỉ lệ chuyển đi trong vòng 2 giờ sau khi nhận",
    "median_dwell_time": "thời gian giữ tiền trung vị",
    "unique_in_counterparties": "số đối tác chuyển đến",
    "unique_out_counterparties": "số đối tác nhận tiền",
    "new_counterparty_ratio": "tỉ lệ đối tác chưa từng giao dịch",
    "median_amount": "số tiền trung vị",
    "p90_amount": "số tiền phân vị 90",
    "amount_std": "độ lệch chuẩn số tiền",
    "repeated_amount_ratio": "tỉ lệ số tiền lặp lại",
    "median_inter_txn_gap": "khoảng cách trung vị giữa hai giao dịch",
    "p10_inter_txn_gap": "khoảng cách ngắn nhất giữa hai giao dịch",
}


def _amount(value: float) -> str:
    """Plain decimal, no grouping separators.

    The evidence critic re-extracts every number from claim text and matches it
    against the cited payload. A thousands separator splits one number into two
    that no payload contains, so the claim would fail its own audit.
    """
    return f"{float(value):.2f}"


def _day(value: Any) -> str:
    return str(value)[:10]


# Screening thresholds for reading a typology signal off the observed window.
# They decide wording only — never the risk score, which stays the detector's.
FAN_COUNTERPARTIES = 5
RAPID_OUTFLOW_PERCENT = 50.0
SHORT_DWELL_HOURS = 24.0
REPEATED_AMOUNT_RATIO = 0.3
RETAINED_OUTFLOW_RATIO = 0.5


def _observed_signals(grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> dict[str, bool]:
    """Which typology signals the collected evidence can actually speak to.

    A signal absent from the returned mapping is one this evidence set cannot
    check — reported as unchecked rather than silently treated as negative.
    """
    signals: dict[str, bool] = {}

    behavior = grouped.get(EvidenceType.BEHAVIOR_FEATURE, [])
    observed = next((item.payload["observed"] for item in behavior if item.payload.get("observed")), None)
    if observed and (observed["incoming_count"] or observed["outgoing_count"]):
        features = behavior[-1].payload.get("features", {})
        dwell = observed.get("median_dwell_hours")
        signals["rapid_outflow"] = observed["rapid_outflow_percent"] >= RAPID_OUTFLOW_PERCENT
        signals["new_counterparties"] = observed["new_counterparties"] > 0
        signals["fan_in"] = observed["unique_in_counterparties"] >= FAN_COUNTERPARTIES
        signals["fan_out"] = observed["unique_out_counterparties"] >= FAN_COUNTERPARTIES
        signals["repeated_amounts"] = float(features.get("repeated_amount_ratio", 0)) >= REPEATED_AMOUNT_RATIO
        if dwell is not None:
            signals["short_dwell_time"] = dwell <= SHORT_DWELL_HOURS
            signals["short_duration"] = signals["short_dwell_time"]
        if observed["inflow_amount"] > 0:
            signals["value_retention"] = (
                observed["outflow_amount"] < RETAINED_OUTFLOW_RATIO * observed["inflow_amount"]
            )

    for item in grouped.get(EvidenceType.GRAPH_PATTERN, []):
        pattern = str(item.payload.get("pattern") or "").upper()
        signals["network_flow"] = bool(pattern)
        signals["directed_cycle"] = "CYCLE" in pattern

    for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
        signals["rule_trigger"] = bool(item.payload.get("triggered_rules"))

    for item in grouped.get(EvidenceType.ANOMALY_EXPLANATION, []):
        if not item.payload.get("available", True):
            continue
        deviating = any(
            abs(float(feature["reference_percentile"]) - 50.0) >= 10.0
            for feature in item.payload.get("top_anomalous_features", [])
        )
        signals["profile_deviation"] = deviating
        signals["volume_deviation"] = deviating

    return signals


def _summary(
    alert: dict[str, Any],
    drivers: list[RiskDriver],
    grouped: dict[EvidenceType, list[EvidenceEnvelope]],
    typologies: list[str],
    missing: list[str],
) -> str:
    """Lead with the behaviour, not with the pipeline."""
    branch = {"anomaly": "mô hình bất thường", "rule": "luật nghiệp vụ", "graph": "đồ thị mạng lưới"}
    primary = branch.get(drivers[0].source, "bằng chứng hiện có") if drivers else "bằng chứng hiện có"

    observed = next(
        (item.payload["observed"] for item in grouped.get(EvidenceType.BEHAVIOR_FEATURE, []) if item.payload.get("observed")),
        None,
    )
    if not observed or not (observed["incoming_count"] or observed["outgoing_count"]):
        headline = (
            f"Cảnh báo do nhánh {primary} sinh ra, nhưng cửa sổ quan sát tính đến mốc ảnh chụp không có "
            "giao dịch nào của tài khoản, nên chưa mô tả được hành vi cụ thể."
        )
    else:
        unit = f" {observed['currency']}" if observed.get("currency") else ""
        headline = (
            f"Trong cửa sổ từ {_day(observed['window_start'])} đến {_day(observed['window_end'])}, tài khoản "
            f"nhận {_amount(observed['inflow_amount'])}{unit} từ {observed['unique_in_counterparties']} đối tác "
            f"và chuyển đi {_amount(observed['outflow_amount'])}{unit} tới "
            f"{observed['unique_out_counterparties']} đối tác"
        )
        if observed["rapid_outflow_percent"] >= RAPID_OUTFLOW_PERCENT:
            headline += (
                f", trong đó {observed['rapid_outflow_percent']}% tiền ra rời tài khoản trong vòng "
                f"{observed['rapid_window_hours']} giờ sau khi nhận"
            )
        headline += f". Cảnh báo được nhánh {primary} chấm điểm."

    tail = f" Nhóm hành vi đối chiếu: {', '.join(typologies)}." if typologies else ""
    if missing:
        tail += " Bản giải thích còn khoảng trống bằng chứng nêu bên dưới."
    return f"{headline}{tail} Kết luận thuộc về chuyên viên rà soát."


def _evidence_by_type(evidence: list[EvidenceEnvelope]) -> dict[EvidenceType, list[EvidenceEnvelope]]:
    grouped: dict[EvidenceType, list[EvidenceEnvelope]] = {}
    for item in evidence:
        grouped.setdefault(item.type, []).append(item)
    return grouped


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _string_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _string_values(nested)


def _mask_identifiers(claim: str, cited: list[EvidenceEnvelope]) -> str:
    """Blank out identifiers before harvesting numbers from claim text.

    An account key like ``070:10042B660`` contains a digit run the number
    regex happily reads as ``70``, which no payload holds numerically — so a
    correctly sourced claim would be flagged unsupported purely for naming the
    counterparty a reviewer needs to see. Identifiers are matched against the
    cited evidence first, longest one wins, so only text the evidence itself
    contains is removed.
    """
    tokens = {token for item in cited for token in _string_values(item.payload) if len(token) > 1}
    for token in sorted(tokens, key=len, reverse=True):
        claim = claim.replace(token, " ")
    return claim


def _numeric_values(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        yield float(value)
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _numeric_values(nested)
    elif isinstance(value, list):
        yield float(len(value))
        for nested in value:
            yield from _numeric_values(nested)


class InvestigationSupervisorAgent:
    name = "investigation_supervisor"

    def __init__(self, service: GeminiService, investigation_id: str):
        self.service = service
        self.investigation_id = investigation_id

    async def plan(
        self,
        *,
        alert: dict[str, Any],
        evidence: list[EvidenceEnvelope],
        validation: ValidationResult | None = None,
    ) -> GeminiCallResult[SupervisorPlan]:
        baseline = self._deterministic_plan(alert=alert, evidence=evidence, validation=validation)
        prompt = get_prompt(self.name)
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context={
                "alert": alert,
                "evidence_collected": [
                    item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content
                ],
                "open_validation": validation.model_dump(mode="json") if validation else None,
                "allow_listed_tool_catalog": InvestigationTools.tool_catalog(),
                "deterministic_safety_candidate": baseline.model_dump(mode="json"),
            },
            untrusted_data=[item.payload for item in evidence if item.is_untrusted_content],
            response_schema=SupervisorPlan,
            fallback_response=baseline,
        )
        # The deterministic baseline is a floor, not a suggestion. A model-authored
        # plan that skips the behaviour and transaction tools leaves the explanation
        # with nothing to describe, so the alert comes back to the reviewer saying
        # only that it scored highly. Baseline decisions run first and keep their
        # slots; the model may add to them, never remove.
        plan = result.output
        decisions = list(baseline.decisions)
        seen = {decision.tool for decision in decisions}
        for decision in plan.decisions:
            if decision.tool not in seen:
                decisions.append(decision)
                seen.add(decision.tool)
        plan = plan.model_copy(update={"decisions": decisions[: get_settings().max_tool_calls]})
        return GeminiCallResult(output=plan, metadata=result.metadata)

    def _deterministic_plan(
        self,
        *,
        alert: dict[str, Any],
        evidence: list[EvidenceEnvelope],
        validation: ValidationResult | None = None,
    ) -> SupervisorPlan:
        """Prioritize detector-specific evidence with a closed tool vocabulary."""
        grouped = _evidence_by_type(evidence)
        decisions: list[ToolDecision] = []
        open_questions: list[str] = []

        if EvidenceType.RISK_BREAKDOWN not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetRiskBreakdown",
                    arguments={"alert_id": alert["alert_id"]},
                    short_rationale="Lấy điểm chính thức và nhánh phát hiện hiện có trước.",
                )
            )

        detector = alert["detector"]
        if detector == "graph":
            if EvidenceType.GRAPH_PATTERN not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetGraphEvidence",
                        arguments={"alert_id": alert["alert_id"]},
                        short_rationale="Đồ thị là nhánh chính; cần bằng chứng có cấu trúc do bộ phát hiện tạo ra.",
                    )
                )
            if EvidenceType.GRAPH_NEIGHBORHOOD not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetGraphNeighborhood",
                        arguments={"account_key": alert["account_key"], "hops": 1, "time_window": "7d"},
                        short_rationale="Thu thập ngữ cảnh giới hạn một chặng mà không yêu cầu mô hình tự duyệt đồ thị.",
                    )
                )
            open_questions.append("Cần có mẫu hình từ bộ phát hiện đồ thị và các cạnh giao dịch tương ứng.")
        elif detector == "ml":
            if EvidenceType.BEHAVIOR_FEATURE not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetAccountBehavior",
                        arguments={"account_key": alert["account_key"], "window": "7d"},
                        short_rationale="Nhánh bất thường cần giá trị đặc trưng nguồn trước khi tạo bản giải thích.",
                    )
                )
            if EvidenceType.ANOMALY_EXPLANATION not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetAnomalyExplanation",
                        arguments={"alert_id": alert["alert_id"], "account_key": alert["account_key"], "window": "7d"},
                        short_rationale="Thu thập mức đóng góp sai lệch đặc trưng được tính tất định cho điểm Isolation Forest.",
                    )
                )
        else:
            if EvidenceType.RULE_TRIGGER not in grouped:
                open_questions.append("Kết quả phát hiện còn thiếu chi tiết luật đã kích hoạt.")

        if EvidenceType.TRANSACTION not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetTransactions",
                    arguments={"account_key": alert["account_key"], "limit": 50},
                    short_rationale="Thu thập tập giao dịch nguồn có giới hạn để đối chiếu bối cảnh cảnh báo.",
                )
            )
        if EvidenceType.TYPOLOGY_MAPPING not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetTypology",
                    arguments={"typology_code": alert["typology_code"]},
                    short_rationale="Đối chiếu nhóm hành vi qua danh mục có phiên bản, không dựa vào kiến thức của lời nhắc.",
                )
            )

        if validation and validation.status == "FAIL":
            for issue in validation.issues:
                if (
                    issue.required_tool
                    and issue.required_tool
                    in {
                        "GetRiskBreakdown",
                        "GetAccountBehavior",
                        "GetTransactions",
                        "GetGraphEvidence",
                        "GetGraphNeighborhood",
                        "GetTypology",
                        "GetAnomalyExplanation",
                    }
                    and all(decision.tool != issue.required_tool for decision in decisions)
                ):
                    # The deterministic workflow never lets critic inject raw
                    # arguments. It derives safe arguments per tool.
                    safe_arguments = {
                        "GetGraphEvidence": {"alert_id": alert["alert_id"]},
                        "GetTransactions": {"account_key": alert["account_key"], "limit": 50},
                        "GetAccountBehavior": {"account_key": alert["account_key"], "window": "7d"},
                        "GetAnomalyExplanation": {
                            "alert_id": alert["alert_id"],
                            "account_key": alert["account_key"],
                            "window": "7d",
                        },
                        "GetTypology": {"typology_code": alert["typology_code"]},
                    }.get(issue.required_tool)
                    if safe_arguments:
                        decisions.append(
                            ToolDecision(
                                tool=issue.required_tool,
                                arguments=safe_arguments,
                                short_rationale=f"Tác tử phản biện yêu cầu bằng chứng được hỗ trợ: {issue.type}.",
                            )
                        )
        settings = get_settings()
        return SupervisorPlan(
            decisions=decisions[: settings.max_tool_calls],
            open_questions=open_questions,
            evidence_sufficient=not decisions and not open_questions,
        )


class ExplanationAgent:
    name = "explanation_agent"

    def __init__(self, service: GeminiService, investigation_id: str):
        self.service = service
        self.investigation_id = investigation_id

    async def explain(self, alert: dict[str, Any], evidence: list[EvidenceEnvelope]) -> GeminiCallResult[Explanation]:
        deterministic = self._deterministic(alert, evidence)
        prompt = get_prompt(self.name)
        trusted = {
            "alert": alert,
            "evidence": [item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content],
            "deterministic_candidate": deterministic.model_dump(mode="json"),
        }
        untrusted = [item.payload for item in evidence if item.is_untrusted_content]
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context=trusted,
            untrusted_data=untrusted,
            response_schema=Explanation,
            fallback_response=deterministic,
            sanitize=self._drop_uncited_facts,
        )
        # The deterministic candidate is sourced by construction: every fact in
        # it was built from a payload it cites. A model response that paraphrases
        # it and loses the citations is not an improvement — the uncited facts
        # get dropped and the reviewer is left with less than the pipeline
        # already knew. The model earns the output by carrying more sourced
        # facts than the floor, not by rewording it.
        sourced = sum(1 for claim in result.output.claims if claim.claim_type == "FACT")
        floor = sum(1 for claim in deterministic.claims if claim.claim_type == "FACT")
        if sourced < floor:
            return GeminiCallResult(output=deterministic, metadata=result.metadata)
        return result

    @staticmethod
    def _drop_uncited_facts(parsed: Any) -> Any:
        """Refuse the offending claim, not the whole investigation.

        A FACT without ``evidence_refs`` is exactly what this system is built
        to reject, but the rejection used to happen at schema validation, which
        discards every well-sourced claim in the same response and fails the
        run. Dropping the single claim keeps that guarantee and leaves the rest
        for the critic to audit. The removal is stated in the output, so a
        reviewer sees that the model asserted something it could not source.
        """
        if not isinstance(parsed, dict) or not isinstance(parsed.get("claims"), list):
            return parsed
        kept = [
            claim
            for claim in parsed["claims"]
            if not (isinstance(claim, dict) and claim.get("claim_type") == "FACT" and not claim.get("evidence_refs"))
        ]
        dropped = len(parsed["claims"]) - len(kept)
        if not dropped:
            return parsed
        note = (
            f"Đã loại {dropped} nhận định loại DỮ KIỆN do không trích dẫn bằng chứng nào. "
            "Nội dung bị loại không được đưa vào bản giải thích."
        )
        return {**parsed, "claims": kept, "missing_information": [*(parsed.get("missing_information") or []), note]}

    @staticmethod
    def _deterministic(alert: dict[str, Any], evidence: list[EvidenceEnvelope]) -> Explanation:
        grouped = _evidence_by_type(evidence)
        risk_ev = grouped[EvidenceType.RISK_BREAKDOWN][-1]
        breakdown = risk_ev.payload
        drivers: list[RiskDriver] = []
        claims: list[Claim] = [
            Claim(
                claim_id=_claim_id(),
                claim=f"Bộ máy phát hiện đã gán điểm rủi ro cuối cùng {breakdown['final_risk_score']:.3f} cho cảnh báo {alert['alert_id']}.",
                claim_type="FACT",
                evidence_refs=[risk_ev.evidence_id],
                confidence=1.0,
            )
        ]
        facts = [claims[0].claim]
        inferences: list[str] = []
        missing: list[str] = []
        typologies: list[str] = []

        for source, component in breakdown["components"].items():
            if component["available"]:
                branch = {
                    "anomaly": "Mô hình phát hiện bất thường",
                    "rule": "Bộ luật nghiệp vụ",
                    "graph": "Bộ phát hiện đồ thị mạng lưới",
                }.get(source, source)
                reason = f"{branch} là nhánh sinh ra cảnh báo này và là nguồn điểm chính thức."
                drivers.append(
                    RiskDriver(
                        source=source,
                        score=component["score"],
                        weight=component["weight"],
                        contribution=component["contribution"],
                        reason=reason,
                        evidence_refs=[risk_ev.evidence_id],
                    )
                )

        for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
            for rule in item.payload.get("triggered_rules", []):
                claim = Claim(
                    claim_id=_claim_id(),
                    claim=f"Yếu tố luật {rule['factor_code']} được ghi nhận với mức đóng góp {float(rule['contribution']):.2f}.",
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(claim)
                facts.append(claim.claim)

        for item in grouped.get(EvidenceType.BEHAVIOR_FEATURE, []):
            observed = item.payload.get("observed")
            if not observed:
                continue
            window = f"từ {_day(observed['window_start'])} đến {_day(observed['window_end'])}"
            unit = f" {observed['currency']}" if observed.get("currency") else ""

            if not observed["incoming_count"] and not observed["outgoing_count"]:
                missing.append(
                    f"Cửa sổ quan sát {window} không có giao dịch nào của tài khoản này, "
                    "nên các đặc trưng hành vi trong cửa sổ đều bằng 0 và không diễn giải được."
                )
                continue

            flow = Claim(
                claim_id=_claim_id(),
                claim=(
                    f"Trong cửa sổ quan sát {window}, tài khoản nhận {_amount(observed['inflow_amount'])}{unit} "
                    f"qua {observed['incoming_count']} giao dịch từ {observed['unique_in_counterparties']} đối tác, "
                    f"và chuyển đi {_amount(observed['outflow_amount'])}{unit} qua {observed['outgoing_count']} "
                    f"giao dịch tới {observed['unique_out_counterparties']} đối tác, "
                    f"trải trên {observed['active_days']} ngày có phát sinh."
                ),
                claim_type="FACT",
                evidence_refs=[item.evidence_id],
                confidence=1.0,
            )
            claims.append(flow)
            facts.append(flow.claim)

            if observed["rapid_outflow_amount"] > 0:
                dwell = observed.get("median_dwell_hours")
                dwell_text = (
                    f" Thời gian giữ tiền trung vị giữa lúc nhận và lần chuyển đi kế tiếp là {dwell} giờ."
                    if dwell is not None
                    else ""
                )
                rapid = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"{_amount(observed['rapid_outflow_amount'])}{unit} được chuyển đi trong vòng "
                        f"{observed['rapid_window_hours']} giờ sau khi nhận, chiếm "
                        f"{observed['rapid_outflow_percent']}% tổng tiền ra của cửa sổ "
                        f"(rapid_outflow_ratio).{dwell_text}"
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(rapid)
                facts.append(rapid.claim)

            if observed["new_counterparties"] > 0:
                fresh = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"{observed['new_counterparties']} trong số các đối tác của cửa sổ này chưa từng giao dịch "
                        "với tài khoản trước mốc cửa sổ (new_counterparty_ratio)."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(fresh)
                facts.append(fresh.claim)

        for item in grouped.get(EvidenceType.ANOMALY_EXPLANATION, []):
            if not item.payload.get("available", True):
                missing.append(
                    "Không có kết quả Isolation Forest cho tài khoản này nên chưa quy được điểm bất thường "
                    "về đặc trưng cụ thể."
                )
                continue
            informative = [
                feature
                for feature in item.payload.get("top_anomalous_features", [])
                if abs(float(feature["reference_percentile"]) - 50.0) >= 10.0
            ]
            if not informative:
                missing.append(
                    "Các đặc trưng của tài khoản không lệch khỏi trung vị nhóm tài khoản cùng cửa sổ, "
                    "nên chưa quy được điểm bất thường về đặc trưng cụ thể."
                )
                continue
            for feature in informative[:3]:
                name = feature["feature"]
                label = FEATURE_LABELS_VI.get(name, name)
                percentile = float(feature["reference_percentile"])
                side = "cao hơn" if percentile >= 50 else "thấp hơn"
                claim = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"So với các tài khoản hoạt động trong cùng cửa sổ, {label} ({name}) của tài khoản ở mức "
                        f"{feature['value']}, nằm tại phân vị {feature['reference_percentile']} — {side} mức "
                        "trung vị của nhóm đối chiếu."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=0.95,
                )
                claims.append(claim)
                facts.append(claim.claim)

        graph_items = grouped.get(EvidenceType.GRAPH_PATTERN, [])
        if alert["detector"] == "graph" and not graph_items:
            missing.append("Chưa có bằng chứng có cấu trúc từ bộ phát hiện đồ thị; không khẳng định mẫu hình đồ thị nào.")
        for item in graph_items:
            pattern = item.payload.get("pattern")
            if not pattern:
                continue
            claim = Claim(
                claim_id=_claim_id(),
                claim=f"Bộ phát hiện đồ thị ghi nhận mẫu hình {pattern} liên quan đến {len(item.payload.get('accounts', []))} tài khoản.",
                claim_type="FACT",
                evidence_refs=[item.evidence_id],
                confidence=1.0,
            )
            claims.append(claim)
            facts.append(claim.claim)

        for item in grouped.get(EvidenceType.TRANSACTION, []):
            records = item.payload.get("items", [])
            if not records:
                missing.append("Không trích xuất được giao dịch nào của tài khoản tính đến mốc ảnh chụp.")
                continue

            account = alert["account_key"]
            for record in sorted(records, key=lambda row: float(row["amount"]), reverse=True)[:3]:
                outgoing = record["source"] == account
                direction = "chuyển" if outgoing else "nhận"
                counterparty = record["destination"] if outgoing else record["source"]
                preposition = "tới" if outgoing else "từ"
                claim = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"Ngày {_day(record['timestamp'])}, tài khoản {direction} "
                        f"{_amount(record['amount'])} {record['currency']} {preposition} {counterparty} "
                        f"qua kênh {record['payment_format']} (mã giao dịch {record['transaction_id']})."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(claim)
                facts.append(claim.claim)

            if item.payload.get("truncated"):
                missing.append(
                    f"Chỉ trích xuất được {len(records)} giao dịch đầu tiên; tài khoản còn giao dịch chưa được "
                    "đưa vào bằng chứng, cần truy vấn thêm trang tiếp theo trước khi kết luận."
                )

        signals = _observed_signals(grouped)
        for item in grouped.get(EvidenceType.TYPOLOGY_MAPPING, []):
            code = item.payload["typology_code"]
            typologies.append(code)
            expected = [*item.payload.get("required_signals", []), *item.payload.get("supporting_signals", [])]
            matched = [name for name in expected if signals.get(name)]
            absent = [name for name in expected if name not in signals]
            unmatched = [name for name in expected if signals.get(name) is False]

            if matched:
                status = (
                    f"khớp {len(matched)} trên {len(expected)} tín hiệu đặc trưng của nhóm này "
                    f"({', '.join(matched)})"
                )
            else:
                status = "chưa khớp tín hiệu đặc trưng nào của nhóm này"
            if unmatched:
                status += f"; không thấy {', '.join(unmatched)}"
            if absent:
                status += f"; chưa kiểm tra được {', '.join(absent)} vì thiếu bằng chứng tương ứng"

            inference = (
                f"Hành vi quan sát được {status}, đối chiếu với nhóm {code} — {item.payload['name']}: "
                f"{item.payload.get('description', '').rstrip('.')}. "
                "Đây là nhận định phục vụ điều tra, không phải kết luận về hành vi rửa tiền."
            )
            inferences.append(inference)
            claims.append(
                Claim(
                    claim_id=_claim_id(),
                    claim=inference,
                    claim_type="INFERENCE",
                    evidence_refs=[item.evidence_id, risk_ev.evidence_id],
                    confidence=0.7 if matched else 0.5,
                )
            )

        # Two evidence items of the same type raise the same gap twice.
        missing = list(dict.fromkeys(missing))
        summary = _summary(alert, drivers, grouped, typologies, missing)
        action = "REQUEST_MORE_INFORMATION" if missing else "ESCALATE_TO_L2"
        return Explanation(
            summary=summary,
            risk_drivers=drivers,
            claims=claims,
            facts=facts,
            inferences=inferences,
            missing_information=missing,
            typologies=typologies,
            confidence=0.75 if missing else 0.9,
            recommended_action=action,
            requires_human_review=True,
        )


class EvidenceCriticAgent:
    name = "evidence_critic"

    def __init__(self, session: Session, service: GeminiService, investigation_id: str):
        self.session = session
        self.service = service
        self.investigation_id = investigation_id
        self.repository = InvestigationRepository(session)

    async def validate(
        self, explanation: Explanation, evidence: list[EvidenceEnvelope]
    ) -> GeminiCallResult[ValidationResult]:
        deterministic = self._deterministic_validate(explanation, evidence)
        prompt = get_prompt(self.name)
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context={
                "explanation": explanation.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content],
                "risk_breakdown": [item.payload for item in evidence if item.type == EvidenceType.RISK_BREAKDOWN],
                "deterministic_backend_validation": deterministic.model_dump(mode="json"),
                "allow_listed_tools": sorted(InvestigationTools.ALLOWED),
            },
            untrusted_data=[item.payload for item in evidence if item.is_untrusted_content],
            response_schema=ValidationResult,
            fallback_response=deterministic,
        )
        gemini = result.output
        issues = list(deterministic.issues)
        seen = {issue.model_dump_json() for issue in issues}
        refuted = 0
        for issue in gemini.issues:
            if self._is_refuted(issue, explanation, evidence):
                refuted += 1
                continue
            serialized = issue.model_dump_json()
            if serialized not in seen:
                issues.append(issue)
                seen.add(serialized)
        if refuted:
            self.repository.add_trace(
                self.investigation_id,
                agent=self.name,
                event_type="VALIDATION_PASS",
                rationale=(
                    f"Đã bỏ qua {refuted} vấn đề do tác tử phản biện Gemini nêu: sổ bằng chứng cho thấy "
                    "các tham chiếu bị coi là thiếu đều tồn tại."
                ),
            )
        if gemini.status == "FAIL" and not gemini.issues:
            issues.append(
                ValidationIssue(
                    type="OTHER",
                    claim="Kết quả của tác tử phản biện Gemini",
                    detail="Tác tử phản biện Gemini trả về trạng thái không đạt nhưng không nêu vấn đề có cấu trúc.",
                )
            )
        status = "FAIL" if issues else "PASS"
        combined = ValidationResult(
            status=status,
            confidence=min(deterministic.confidence, gemini.confidence),
            issues=issues,
            missing_evidence=list(dict.fromkeys([*deterministic.missing_evidence, *gemini.missing_evidence])),
            unsupported_claims=list(dict.fromkeys([*deterministic.unsupported_claims, *gemini.unsupported_claims])),
            next_action="BUILD_CASE_PACKAGE" if status == "PASS" else "RETURN_TO_INVESTIGATION",
        )
        return GeminiCallResult(output=combined, metadata=result.metadata)

    @staticmethod
    def _is_refuted(
        issue: ValidationIssue, explanation: Explanation, evidence: list[EvidenceEnvelope]
    ) -> bool:
        """Drop a critic objection the evidence ledger positively disproves.

        The critic may only ever be a second opinion on top of the ledger. Left
        unchecked, one hallucinated "this evidence ID does not exist" fails an
        investigation whose citations are all present and verified, and the
        reviewer is told there is no explanation at all. Only MISSING_EVIDENCE
        is refutable this way, and only when every reference on the named claim
        resolves — a genuine gap still fails the run.
        """
        if issue.type != "MISSING_EVIDENCE":
            return False
        known = {item.evidence_id for item in evidence}
        if issue.evidence_ref and issue.evidence_ref not in known:
            return False
        return any(
            claim.claim == issue.claim and claim.evidence_refs and all(ref in known for ref in claim.evidence_refs)
            for claim in explanation.claims
        )

    def _deterministic_validate(self, explanation: Explanation, evidence: list[EvidenceEnvelope]) -> ValidationResult:
        by_id = {item.evidence_id: item for item in evidence}
        issues: list[ValidationIssue] = []

        for claim in explanation.claims:
            missing_refs = [reference for reference in claim.evidence_refs if reference not in by_id]
            if missing_refs or (claim.claim_type == "FACT" and not claim.evidence_refs):
                issues.append(
                    ValidationIssue(
                        type="MISSING_EVIDENCE",
                        claim=claim.claim,
                        evidence_ref=missing_refs[0] if missing_refs else None,
                        detail="Nhận định không liên kết được với bằng chứng trong sổ điều tra này.",
                    )
                )
                continue
            cited = [by_id[reference] for reference in claim.evidence_refs]
            lower = claim.claim.lower()
            if claim.claim_type == "FACT":
                cited_numbers = [number for item in cited for number in _numeric_values(item.payload)]
                claim_numbers = re.findall(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])", _mask_identifiers(claim.claim, cited))
                unsupported_numbers = [
                    float(number)
                    for number in claim_numbers
                    if not any(
                        abs(float(number) - cited_number)
                        <= (0.5 * 10 ** -len(number.partition(".")[2]) if "." in number else 1e-6) + 1e-9
                        for cited_number in cited_numbers
                    )
                ]
                if unsupported_numbers:
                    issues.append(
                        ValidationIssue(
                            type="UNSUPPORTED_CLAIM",
                            claim=claim.claim,
                            detail=f"Numeric values {unsupported_numbers} do not occur in cited evidence.",
                        )
                    )
            if "money laundering" in lower and claim.claim_type == "FACT":
                issues.append(
                    ValidationIssue(
                        type="UNSUPPORTED_CLAIM",
                        claim=claim.claim,
                        detail="Tác tử không được trình bày kết luận rửa tiền như một dữ kiện.",
                    )
                )
            if ("cycle" in lower or "graph detector" in lower or "graph pattern" in lower) and not any(
                item.type == EvidenceType.GRAPH_PATTERN and item.source == "graph_detector" for item in cited
            ):
                issues.append(
                    ValidationIssue(
                        type="UNSUPPORTED_CLAIM",
                        claim=claim.claim,
                        required_tool="GetGraphEvidence",
                        detail="Nhận định về đồ thị cần bằng chứng có cấu trúc từ bộ phát hiện đồ thị.",
                    )
                )
            if re.search(r"\bT(?:0[1-9]|10)\b", claim.claim) and not any(
                item.type == EvidenceType.TYPOLOGY_MAPPING for item in cited
            ):
                issues.append(
                    ValidationIssue(
                        type="INVALID_TYPOLOGY",
                        claim=claim.claim,
                        required_tool="GetTypology",
                        detail="Diễn giải nhóm hành vi phải trích dẫn ánh xạ trong danh mục.",
                    )
                )

        for driver in explanation.risk_drivers:
            expected = round(driver.score * driver.weight, 6)
            if abs(driver.contribution - expected) > 1e-6:
                issues.append(
                    ValidationIssue(
                        type="INVALID_SCORE_CONTRIBUTION",
                        claim=f"{driver.source} contribution {driver.contribution}",
                        evidence_ref=driver.evidence_refs[0] if driver.evidence_refs else None,
                        detail=f"Expected score × weight = {expected}.",
                    )
                )
            risk_sources = [
                by_id[reference]
                for reference in driver.evidence_refs
                if reference in by_id and by_id[reference].type == EvidenceType.RISK_BREAKDOWN
            ]
            component = risk_sources[0].payload.get("components", {}).get(driver.source) if risk_sources else None
            if not component or any(
                abs(float(component[field]) - getattr(driver, field)) > 1e-6
                for field in ("score", "weight", "contribution")
            ):
                issues.append(
                    ValidationIssue(
                        type="INVALID_SCORE_CONTRIBUTION",
                        claim=f"{driver.source} risk driver",
                        evidence_ref=driver.evidence_refs[0] if driver.evidence_refs else None,
                        detail="Giá trị yếu tố rủi ro không khớp chi tiết từ Bộ máy phát hiện được trích dẫn.",
                    )
                )

        for item in evidence:
            if item.type != EvidenceType.TRANSACTION:
                continue
            for record in item.payload.get("items", []):
                row = (
                    self.session.execute(
                        text(
                            """SELECT occurred_at, from_account_key, to_account_key, amount, currency, channel
                                 FROM transaction WHERE transaction_id = :id"""
                        ),
                        {"id": int(record["transaction_id"])},
                    )
                    .mappings()
                    .first()
                )
                if not row or any(
                    [
                        row["from_account_key"] != record["source"],
                        row["to_account_key"] != record["destination"],
                        float(row["amount"]) != float(record["amount"]),
                        row["currency"] != record["currency"],
                        row["channel"] != record["payment_format"],
                        row["occurred_at"].isoformat() != str(record["timestamp"]).replace("Z", "+00:00"),
                    ]
                ):
                    issues.append(
                        ValidationIssue(
                            type="MISSING_SOURCE_RECORD",
                            claim=f"Transaction {record['transaction_id']}",
                            evidence_ref=item.evidence_id,
                            required_tool="GetTransactions",
                            detail="Bằng chứng giao dịch không khớp bản ghi trong cơ sở dữ liệu nguồn.",
                        )
                    )

        for item in evidence:
            if item.type != EvidenceType.GRAPH_PATTERN:
                continue
            for edge in item.payload.get("edges", []):
                row = (
                    self.session.execute(
                        text(
                            """SELECT from_account_key, to_account_key FROM transaction
                                 WHERE transaction_id = :id"""
                        ),
                        {"id": int(edge["transaction_id"])},
                    )
                    .mappings()
                    .first()
                )
                if not row or row["from_account_key"] != edge["from"] or row["to_account_key"] != edge["to"]:
                    issues.append(
                        ValidationIssue(
                            type="MISSING_SOURCE_RECORD",
                            claim=f"Graph edge transaction {edge['transaction_id']}",
                            evidence_ref=item.evidence_id,
                            required_tool="GetGraphEvidence",
                            detail="Cạnh từ bộ phát hiện đồ thị không khớp giao dịch nguồn.",
                        )
                    )

        # A graph-detector alert without its detector evidence is a critical
        # gap even if the explanation correctly abstains from claiming a pattern.
        risk_items = [item for item in evidence if item.type == EvidenceType.RISK_BREAKDOWN]
        graph_primary = any(item.payload.get("components", {}).get("graph", {}).get("available") for item in risk_items)
        if graph_primary and not any(item.type == EvidenceType.GRAPH_PATTERN for item in evidence):
            issues.append(
                ValidationIssue(
                    type="MISSING_EVIDENCE",
                    claim="Primary graph detector signal",
                    required_tool="GetGraphEvidence",
                    detail="Có điểm đồ thị nhưng chưa có bằng chứng có cấu trúc về mẫu hình/cạnh tương ứng.",
                )
            )

        status = "FAIL" if issues else "PASS"
        return ValidationResult(
            status=status,
            confidence=0.98 if not issues else 0.9,
            issues=issues,
            missing_evidence=[issue.detail for issue in issues if issue.type == "MISSING_EVIDENCE"],
            unsupported_claims=[issue.claim for issue in issues if issue.type == "UNSUPPORTED_CLAIM"],
            next_action="BUILD_CASE_PACKAGE" if status == "PASS" else "RETURN_TO_INVESTIGATION",
        )
