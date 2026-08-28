import re
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.investigation.agents import EvidenceCriticAgent, ExplanationAgent, InvestigationSupervisorAgent
from src.investigation.llm import FakeGeminiService
from src.investigation.schemas import (
    Claim,
    EvidenceEnvelope,
    EvidenceIntegrity,
    EvidenceType,
    Explanation,
    RiskDriver,
    ValidationIssue,
    ValidationResult,
)


def evidence(evidence_type: EvidenceType, payload: dict, *, source: str = "detection_engine") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=f"EV-{evidence_type.value}",
        type=evidence_type,
        source=source,
        account_key="001:A",
        payload=payload,
        created_at=datetime.now(UTC),
        integrity=EvidenceIntegrity(source_system=source, source_record_ids=["record-1"], content_hash="a" * 64),
    )


def alert(detector: str) -> dict:
    return {
        "alert_id": "ALT-1",
        "account_key": "001:A",
        "detector": detector,
        "typology_code": "T03" if detector == "graph" else "T02",
    }


def risk_evidence(detector: str) -> EvidenceEnvelope:
    source = {"rule": "rule", "ml": "anomaly", "graph": "graph"}[detector]
    components = {
        name: {
            "score": 0.96 if name == source else 0,
            "weight": 1 if name == source else 0,
            "contribution": 0.96 if name == source else 0,
            "available": name == source,
            "source_ref": "alert:ALT-1" if name == source else None,
        }
        for name in ("rule", "anomaly", "graph")
    }
    return evidence(
        EvidenceType.RISK_BREAKDOWN,
        {
            "alert_id": "ALT-1",
            "final_risk_score": 0.96,
            # Cùng một điểm theo thang console. Bản giải thích trích số này chứ
            # không tự nhân 0,96 lên, để bộ kiểm chứng tìm thấy nó trong bằng chứng.
            "final_risk_score_100": 96.0,
            "fusion_available": False,
            "components": components,
        },
    )


@pytest.mark.asyncio
async def test_graph_heavy_alert_requests_graph_evidence_before_unrelated_tools():
    agent = InvestigationSupervisorAgent(FakeGeminiService(), "INV-1")
    plan = (await agent.plan(alert=alert("graph"), evidence=[])).output
    tools = [decision.tool for decision in plan.decisions]
    assert tools[0] == "GetRiskBreakdown"
    assert tools.index("GetGraphEvidence") < tools.index("GetTransactions")


@pytest.mark.asyncio
async def test_anomaly_heavy_alert_prioritizes_behavior_and_anomaly_explanation():
    agent = InvestigationSupervisorAgent(FakeGeminiService(), "INV-1")
    plan = (await agent.plan(alert=alert("ml"), evidence=[risk_evidence("ml")])).output
    tools = [decision.tool for decision in plan.decisions]
    assert tools[:2] == ["GetAccountBehavior", "GetAnomalyExplanation"]


@pytest.mark.asyncio
async def test_rule_heavy_alert_collects_transactions_and_catalog_mapping():
    agent = InvestigationSupervisorAgent(FakeGeminiService(), "INV-1")
    plan = (await agent.plan(alert=alert("rule"), evidence=[risk_evidence("rule")])).output
    assert [decision.tool for decision in plan.decisions] == ["GetTransactions", "GetTypology"]


def test_explanation_agent_never_claims_missing_graph_pattern():
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    explanation = agent._deterministic(alert("graph"), [risk_evidence("graph")])
    assert all("CYCLE" not in claim.claim for claim in explanation.claims)
    assert any("bộ phát hiện đồ thị" in item for item in explanation.missing_information)


@pytest.mark.asyncio
async def test_critic_fails_graph_claim_without_graph_detector_evidence():
    risk = risk_evidence("rule")
    explanation = Explanation(
        summary="Review required",
        risk_drivers=[
            RiskDriver(
                source="rule", score=0.96, weight=1, contribution=0.96, reason="rule", evidence_refs=[risk.evidence_id]
            )
        ],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="The account participates in a CYCLE graph pattern.",
                claim_type="FACT",
                evidence_refs=[risk.evidence_id],
                confidence=1,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.8,
        recommended_action="REQUEST_MORE_INFORMATION",
    )
    agent = EvidenceCriticAgent(MagicMock(), FakeGeminiService(), "INV-1")
    result = (await agent.validate(explanation, [risk])).output
    assert result.status == "FAIL"
    assert result.issues[0].required_tool == "GetGraphEvidence"


@pytest.mark.asyncio
async def test_critic_passes_grounded_score_claim():
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    result = (await EvidenceCriticAgent(MagicMock(), FakeGeminiService(), "INV-1").validate(explanation, [risk])).output
    assert result.status == "PASS"
    assert result.next_action == "BUILD_CASE_PACKAGE"


@pytest.mark.asyncio
async def test_critic_rejects_invented_number_even_with_a_real_citation():
    risk = risk_evidence("rule")
    explanation = Explanation(
        summary="Review required",
        risk_drivers=[
            RiskDriver(
                source="rule",
                score=0.96,
                weight=1,
                contribution=0.96,
                reason="rule",
                evidence_refs=[risk.evidence_id],
            )
        ],
        claims=[
            Claim(
                claim_id="CLM-99",
                claim="The account sent 999 transactions.",
                claim_type="FACT",
                evidence_refs=[risk.evidence_id],
                confidence=1,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.8,
        recommended_action="REQUEST_MORE_INFORMATION",
    )
    agent = EvidenceCriticAgent(MagicMock(), FakeGeminiService(), "INV-1")
    result = (await agent.validate(explanation, [risk])).output
    assert result.status == "FAIL"
    assert "999" in result.issues[0].detail


@pytest.mark.asyncio
async def test_all_three_agents_call_the_shared_gemini_boundary():
    service = FakeGeminiService()
    risk = risk_evidence("rule")
    supervisor = InvestigationSupervisorAgent(service, "INV-1")
    explanation_agent = ExplanationAgent(service, "INV-1")
    await supervisor.plan(alert=alert("rule"), evidence=[risk])
    explanation = (await explanation_agent.explain(alert("rule"), [risk])).output
    await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])

    assert [call["agent_name"] for call in service.calls] == [
        "investigation_supervisor",
        "explanation_agent",
        "evidence_critic",
    ]
    assert all(re.fullmatch(r"[a-z-]+-v\d+-vi", call["prompt_version"]) for call in service.calls)


def behavior_evidence(**overrides) -> EvidenceEnvelope:
    observed = {
        "window_start": "2022-08-25T00:00:00Z",
        "window_end": "2022-09-01T00:29:00Z",
        "window_days": 7,
        "currency": "USD",
        "inflow_amount": 41000.5,
        "outflow_amount": 39900.25,
        "largest_amount": 8433.84,
        "incoming_count": 9,
        "outgoing_count": 12,
        "unique_in_counterparties": 6,
        "unique_out_counterparties": 8,
        "new_counterparties": 4,
        "rapid_outflow_amount": 37000.75,
        "rapid_outflow_percent": 92.73,
        "rapid_window_hours": 2,
        "median_dwell_hours": 1.25,
        "active_days": 3,
        **overrides,
    }
    return evidence(
        EvidenceType.BEHAVIOR_FEATURE,
        {
            "account_key": "001:A",
            "window": "7d",
            "features": {"repeated_amount_ratio": 0.4},
            "observed": observed,
        },
        source="feature_service",
    )


def test_explanation_describes_money_movement_not_pipeline_mechanics():
    explanation = ExplanationAgent._deterministic(alert("ml"), [risk_evidence("ml"), behavior_evidence()])
    facts = " ".join(claim.claim for claim in explanation.claims if claim.claim_type == "FACT")

    # Số tiền có dấu tách hàng nghìn để đọc được bằng mắt; bộ kiểm số chuẩn hoá
    # lại trước khi đối chiếu với bằng chứng.
    assert "41\u202f000.50" in facts and "39\u202f900.25" in facts
    assert "6 đối tác" in facts and "8 đối tác" in facts
    # Tỉ lệ làm tròn tới phần trăm nguyên: cùng một phép đo phải hiện MỘT con số
    # ở mọi chỗ, không phải "93%" ở tóm tắt và "92.73%" ở dữ kiện.
    assert "93% tổng tiền ra" in facts and "2 giờ" in facts
    # The old wording reported tool plumbing instead of account behaviour.
    assert "bản ghi để rà soát" not in facts


def test_explanation_reports_an_empty_window_instead_of_inventing_zero_features():
    empty = behavior_evidence(incoming_count=0, outgoing_count=0, inflow_amount=0, outflow_amount=0)
    explanation = ExplanationAgent._deterministic(alert("ml"), [risk_evidence("ml"), empty])

    assert not any("nhận 0.00" in claim.claim for claim in explanation.claims)
    assert any("không có giao dịch" in item for item in explanation.missing_information)


def test_anomaly_claim_is_skipped_when_the_account_sits_at_the_reference_median():
    flat = evidence(
        EvidenceType.ANOMALY_EXPLANATION,
        {
            "available": True,
            "top_anomalous_features": [
                {"feature": "txn_count", "value": 0.0, "reference_percentile": 50.0},
            ],
        },
        source="anomaly_explanation_service",
    )
    explanation = ExplanationAgent._deterministic(alert("ml"), [risk_evidence("ml"), flat])

    assert not any("txn_count" in claim.claim for claim in explanation.claims)
    assert any("không lệch khỏi trung vị" in item for item in explanation.missing_information)


def test_uncited_fact_is_dropped_without_discarding_the_rest_of_the_response():
    parsed = {
        "claims": [
            {"claim_id": "CLM-1", "claim": "Không nguồn", "claim_type": "FACT", "evidence_refs": []},
            {"claim_id": "CLM-2", "claim": "Có nguồn", "claim_type": "FACT", "evidence_refs": ["EV-1"]},
            {"claim_id": "CLM-3", "claim": "Suy luận", "claim_type": "INFERENCE", "evidence_refs": []},
        ],
        "missing_information": [],
    }
    cleaned = ExplanationAgent._drop_uncited_facts(parsed)

    assert [claim["claim_id"] for claim in cleaned["claims"]] == ["CLM-2", "CLM-3"]
    assert any("Đã loại 1" in item for item in cleaned["missing_information"])


def test_critic_accepts_a_sourced_claim_that_names_a_counterparty_account():
    transactions = evidence(
        EvidenceType.TRANSACTION,
        {
            "items": [
                {
                    "transaction_id": "12217",
                    "source": "001:A",
                    "destination": "070:10042B660",
                    "timestamp": "2022-09-01T00:29:00Z",
                    "amount": 8433.84,
                    "currency": "USD",
                    "payment_format": "Cash",
                }
            ]
        },
        source="transaction_service",
    )
    explanation = Explanation(
        summary="Cần rà soát",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim=(
                    "Ngày 2022-09-01, tài khoản chuyển 8433.84 USD tới 070:10042B660 "
                    "qua kênh Cash (mã giao dịch 12217)."
                ),
                claim_type="FACT",
                evidence_refs=[transactions.evidence_id],
                confidence=1.0,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.9,
        recommended_action="ESCALATE_TO_L2",
    )
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    critic = EvidenceCriticAgent(session, FakeGeminiService(), "INV-1")
    result = critic._deterministic_validate(explanation, [transactions])

    # The account key's digit run must not be read as an unsupported number.
    assert not [issue for issue in result.issues if issue.type == "UNSUPPORTED_CLAIM"]


def test_critic_reads_a_negative_decimal_as_one_number():
    """Số âm phải được đọc trọn vẹn, không bị cắt lấy phần thập phân.

    Ca thật từ INV-3cee3f9e357c4c0cbb1c: câu nêu ``net_flow`` bằng ``-16.466031``
    bị đánh trượt với lý do "Numeric values [466031.0] do not occur in cited
    evidence". 466031 không phải con số nào trong câu — nó là phần thập phân bị
    tách rời. Mọi cảnh báo có dòng tiền ròng âm đều vấp lỗi này ở cả ba vòng lặp
    rồi kết thúc bằng INSUFFICIENT_EVIDENCE.
    """
    behavior = evidence(
        EvidenceType.BEHAVIOR_FEATURE,
        {"features": {"net_flow": -16.466031, "net_flow_percentile": 0.4}},
        source="behavior_service",
    )
    explanation = Explanation(
        summary="Cần rà soát",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="Dòng tiền ròng của tài khoản ở mức -16.466031, nằm tại phân vị 0.4.",
                claim_type="FACT",
                evidence_refs=[behavior.evidence_id],
                confidence=1.0,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.9,
        recommended_action="ESCALATE_TO_L2",
    )
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    critic = EvidenceCriticAgent(session, FakeGeminiService(), "INV-1")
    result = critic._deterministic_validate(explanation, [behavior])

    assert not [issue for issue in result.issues if issue.type == "UNSUPPORTED_CLAIM"]


def test_critic_still_catches_a_number_absent_from_evidence():
    """Chốt chặn cho hướng ngược lại: nới regex không được làm hỏng việc kiểm số."""
    behavior = evidence(
        EvidenceType.BEHAVIOR_FEATURE,
        {"features": {"net_flow": -16.466031}},
        source="behavior_service",
    )
    explanation = Explanation(
        summary="Cần rà soát",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="Dòng tiền ròng của tài khoản ở mức -99.5.",
                claim_type="FACT",
                evidence_refs=[behavior.evidence_id],
                confidence=1.0,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.9,
        recommended_action="ESCALATE_TO_L2",
    )
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    critic = EvidenceCriticAgent(session, FakeGeminiService(), "INV-1")
    result = critic._deterministic_validate(explanation, [behavior])

    assert [issue for issue in result.issues if issue.type == "UNSUPPORTED_CLAIM"]


@pytest.mark.asyncio
async def test_critic_ignores_a_hallucinated_missing_evidence_objection():
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    hallucination = ValidationResult(
        status="FAIL",
        confidence=0.85,
        issues=[
            ValidationIssue(
                type="MISSING_EVIDENCE",
                claim=explanation.claims[0].claim,
                detail="Bằng chứng tham chiếu không tồn tại trong tập dữ liệu cung cấp.",
            )
        ],
        missing_evidence=[],
        unsupported_claims=[],
        next_action="RETURN_TO_INVESTIGATION",
    )
    service = FakeGeminiService({"evidence_critic": hallucination.model_dump(mode="json")})
    result = (await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])).output

    assert result.status == "PASS"
    assert result.issues == []


@pytest.mark.asyncio
async def test_critic_objection_is_refuted_whatever_label_it_arrives_under():
    """Cáo buộc "mã này không tồn tại" bị bác bỏ kể cả khi mang nhãn khác.

    Quan sát trên hồ sơ thật: tác tử phản biện nêu đúng cáo buộc ấy dưới nhãn
    UNSUPPORTED_CLAIM thay vì MISSING_EVIDENCE, và lọt qua bộ lọc chỉ xét nhãn.
    Hệ quả là hồ sơ có đủ chứng cứ vẫn bị đánh trượt.
    """
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    mislabelled = ValidationResult(
        status="FAIL",
        confidence=0.9,
        issues=[
            ValidationIssue(
                type="UNSUPPORTED_CLAIM",
                claim=explanation.claims[0].claim,
                detail=f"Evidence_ref {risk.evidence_id} không tồn tại trong evidence_index.",
            )
        ],
        missing_evidence=[],
        unsupported_claims=[],
        next_action="RETURN_TO_INVESTIGATION",
    )
    service = FakeGeminiService({"evidence_critic": mislabelled.model_dump(mode="json")})
    result = (await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])).output

    assert result.status == "PASS"
    assert result.issues == []


@pytest.mark.asyncio
async def test_critic_does_not_fail_a_truncation_the_explanation_already_declared():
    """Hạn chế đã tự khai không được tính là khiếm khuyết.

    Sổ giao dịch cắt ở 50 dòng là giới hạn phân trang đã biết và bản giải thích
    ghi nó ở mục thông tin còn thiếu. Tác tử phản biện nêu lại rồi đánh trượt cả
    phiên là đếm hai lần một hạn chế đã công bố.
    """
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    explanation.missing_information.append(
        "Chỉ trích xuất được 50 giao dịch đầu tiên; cần truy vấn thêm trang tiếp theo."
    )
    objection = ValidationResult(
        status="FAIL",
        confidence=0.9,
        issues=[
            ValidationIssue(
                type="OTHER",
                claim="Sổ giao dịch",
                detail="Dữ liệu giao dịch bị cắt bớt (chỉ hiển thị 50 giao dịch).",
            )
        ],
        missing_evidence=[],
        unsupported_claims=[],
        next_action="RETURN_TO_INVESTIGATION",
    )
    service = FakeGeminiService({"evidence_critic": objection.model_dump(mode="json")})
    result = (await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])).output

    assert result.status == "PASS"


@pytest.mark.asyncio
async def test_critic_objection_about_a_genuinely_absent_id_still_fails():
    """Bác bỏ chỉ dành cho mã có thật. Mã bịa vẫn phải làm phiên trượt."""
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    genuine = ValidationResult(
        status="FAIL",
        confidence=0.9,
        issues=[
            ValidationIssue(
                type="UNSUPPORTED_CLAIM",
                claim=explanation.claims[0].claim,
                detail="Evidence_ref EV-deadbeefdeadbeef không tồn tại trong evidence_index.",
            )
        ],
        missing_evidence=[],
        unsupported_claims=[],
        next_action="RETURN_TO_INVESTIGATION",
    )
    service = FakeGeminiService({"evidence_critic": genuine.model_dump(mode="json")})
    result = (await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])).output

    assert result.status == "FAIL"


@pytest.mark.asyncio
async def test_critic_keeps_a_missing_evidence_objection_it_cannot_refute():
    risk = risk_evidence("rule")
    explanation = ExplanationAgent(FakeGeminiService(), "INV-1")._deterministic(alert("rule"), [risk])
    genuine = ValidationResult(
        status="FAIL",
        confidence=0.85,
        issues=[
            ValidationIssue(
                type="MISSING_EVIDENCE",
                claim="Một nhận định không nằm trong bản giải thích",
                detail="Không có bằng chứng nào chứng minh nội dung này.",
            )
        ],
        missing_evidence=[],
        unsupported_claims=[],
        next_action="RETURN_TO_INVESTIGATION",
    )
    service = FakeGeminiService({"evidence_critic": genuine.model_dump(mode="json")})
    result = (await EvidenceCriticAgent(MagicMock(), service, "INV-1").validate(explanation, [risk])).output

    assert result.status == "FAIL"


@pytest.mark.asyncio
async def test_a_thinner_model_response_does_not_replace_the_sourced_baseline():
    risk = risk_evidence("ml")
    behavior = behavior_evidence()
    thin = Explanation(
        summary="Bản mỏng",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="Tài khoản có rủi ro cao.",
                claim_type="INFERENCE",
                evidence_refs=[],
                confidence=0.6,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.6,
        recommended_action="ESCALATE_TO_L2",
    )
    service = FakeGeminiService({"explanation_agent": thin.model_dump(mode="json")})
    output = (await ExplanationAgent(service, "INV-1").explain(alert("ml"), [risk, behavior])).output

    facts = [claim for claim in output.claims if claim.claim_type == "FACT"]
    assert len(facts) > 1
    assert all(claim.evidence_refs for claim in facts)


# --- Những lỗi đã đo được trên hồ sơ thật, khoá lại để không quay lại ---------


def _behavior(*, incoming: int, outgoing: int, window_days: int = 30) -> EvidenceEnvelope:
    return evidence(
        EvidenceType.BEHAVIOR_FEATURE,
        {
            "account_key": "001:A",
            "window": f"{window_days}d",
            "features": {},
            "observed": {
                "window_start": "2022-08-29T00:00:00Z",
                "window_end": "2022-09-28T00:00:00Z",
                "window_days": window_days,
                "currency": "Euro",
                "inflow_amount": 100.0 if incoming else 0.0,
                "outflow_amount": 50.0 if outgoing else 0.0,
                "largest_amount": 100.0,
                "incoming_count": incoming,
                "outgoing_count": outgoing,
                "unique_in_counterparties": 1 if incoming else 0,
                "unique_out_counterparties": 1 if outgoing else 0,
                "new_counterparties": 0,
                "rapid_outflow_amount": 0.0,
                "rapid_outflow_percent": 0.0,
                "rapid_window_hours": 2,
                "median_dwell_hours": None,
                "active_days": 1,
            },
        },
        source="feature_service",
    )


def _transactions(items: list[dict]) -> EvidenceEnvelope:
    return evidence(
        EvidenceType.TRANSACTION,
        {"items": items, "limit": 50, "next_cursor": None, "truncated": False},
        source="transaction_service",
    )


def _tx(tid: str, *, out: bool, amount: float, src_country: str | None = None, dst_country: str | None = None) -> dict:
    return {
        "transaction_id": tid,
        "source": "001:A" if out else "002:B",
        "destination": "002:B" if out else "001:A",
        "timestamp": "2022-09-16T00:00:00Z",
        "amount": amount,
        "currency": "Euro",
        "payment_format": "CHEQUE",
        "source_country": src_country,
        "destination_country": dst_country,
    }


def test_summary_never_denies_transactions_that_the_ledger_shows():
    """Câu mở đầu không được nói "không có giao dịch nào" khi sổ có giao dịch.

    Đây là mâu thuẫn chuyên viên nhìn thấy đầu tiên trên màn hình chi tiết cảnh
    báo: câu tóm tắt phủ nhận, ba dòng dữ kiện ngay bên dưới liệt kê giao dịch
    có ngày, có số tiền, có mã. Hai phần đọc hai nguồn khác nhau và chỉ phần đầu
    rỗng — nói "không có giao dịch nào của tài khoản" là sai phạm vi.
    """
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    explanation = agent._deterministic(
        alert("mega_pna"),
        [
            risk_evidence("graph"),
            _behavior(incoming=0, outgoing=0),
            _transactions([_tx("16017462", out=True, amount=30101.17)]),
        ],
    )
    assert "không có giao dịch nào của tài khoản" not in explanation.summary
    assert "sổ giao dịch của tài khoản có 1 giao dịch" in explanation.summary


#: Từ ngữ kỹ thuật không được xuất hiện trong câu chuyên viên tuân thủ đọc.
#: Tên mô hình và mã nhóm hành vi vẫn còn nguyên ở bảng phân rã điểm và sổ bằng
#: chứng — chỗ kiểm toán viên tìm đến — chỉ là không chiếm chỗ câu đầu tiên.
_JARGON = ("MEGA-PNA", "mega_pna", "geo_rule", "nhánh", "cửa sổ đặc trưng", "ảnh chụp", "detector")


def test_the_summary_speaks_to_a_compliance_officer_not_an_engineer():
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    risk = risk_evidence("graph")
    risk.payload["components"]["mega_pna"] = {
        "score": 1.0,
        "weight": 1.0,
        "contribution": 1.0,
        "available": True,
        "source_ref": "alert:ALT-1",
    }
    risk.payload["components"]["graph"]["available"] = False
    explanation = agent._deterministic(alert("mega_pna"), [risk, _behavior(incoming=1, outgoing=1)])
    for word in _JARGON:
        assert word not in explanation.summary, word
    assert "T02" not in explanation.summary


def test_the_summary_says_what_the_account_did_with_the_money():
    """Câu quan trọng nhất: rốt cuộc tài khoản này làm gì.

    Bản cũ kể đủ số liệu rồi dừng, để chuyên viên tự ghép thành câu chuyện. Một
    người mở ba trăm cảnh báo mỗi ngày không có thời gian làm việc đó.
    """
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    funnel = _behavior(incoming=1, outgoing=1)
    funnel.payload["observed"].update(
        {
            # 6 nguồn: vượt NGƯỠNG DUY NHẤT của chữ "nhiều" (FAN_COUNTERPARTIES).
            # Trước đây văn xuôi dùng ngưỡng riêng là 3, nên cùng một trang vừa
            # gọi "nhiều nguồn" vừa ghi "chưa đạt ngưỡng ≥ 5".
            "unique_in_counterparties": 6,
            "unique_out_counterparties": 1,
            "inflow_amount": 19967.46,
            "outflow_amount": 712081.05,
        }
    )
    explanation = agent._deterministic(alert("mega_pna"), [risk_evidence("graph"), funnel])
    assert "Hình phễu" in explanation.summary
    assert "điểm gom tiền" in explanation.summary


def _geo_rule_evidence() -> EvidenceEnvelope:
    return evidence(
        EvidenceType.RULE_TRIGGER,
        {
            "alert_id": "ALT-1",
            "detector": "geo_rule",
            "triggered_rules": [
                {
                    "factor_code": "GEO_CORRIDOR",
                    "factor_label": "Hành lang UK→UAE — rủi ro gấp 5.1 lần mức nền",
                    "contribution": 61.64,
                    "weight": 1.0,
                }
            ],
            "geo_context": {
                "corridor": "UK→UAE",
                "from_country": "UK",
                "to_country": "UAE",
                "cross_border": True,
                "corridor_transactions": 27372,
                "corridor_label_rate": 0.005224,
                "corridor_label_percent": 0.52,
                "lift_vs_all": 5.136,
                "lift_vs_cross_border": 1.678,
                "baseline_all": 0.0010171,
                "baseline_all_percent": 0.1,
                "baseline_cross_border": 0.0031132,
                "baseline_cross_border_percent": 0.31,
                "country_count": 3,
                "cash_count": 0,
                "fx_count": 3,
                "window_transactions": 8,
                "driving_transaction_id": "28104974",
            },
        },
        source="geo_rule_engine",
    )


def test_geo_alert_names_both_countries_and_the_baseline_it_compares_against():
    """ "Gấp 5,1 lần mức nền" không kiểm chứng được nếu không nói mức nền là gì."""
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    explanation = agent._deterministic(
        alert("geo_rule"), [risk_evidence("rule"), _geo_rule_evidence(), _behavior(incoming=1, outgoing=1)]
    )
    corridor = next(claim for claim in explanation.claims if "UK → UAE" in claim.claim)
    assert "0.52%" in corridor.claim
    assert "0.31%" in corridor.claim and "xuyên biên giới" in corridor.claim
    assert "0.1%" in corridor.claim
    # Không dấu phân cách hàng nghìn: "27.372" bị đọc thành 27,372.
    assert "27372" in corridor.claim


def test_geo_signals_come_from_the_corridor_that_raised_the_alert():
    """T06 đòi jurisdiction_signal; không nhánh nào sinh ra thì mọi cảnh báo địa
    lý đều kết luận "chưa kiểm tra được" rồi trượt phản biện — cả 5.004 cảnh báo.
    """
    from src.investigation.agents import _evidence_by_type, _observed_signals

    grouped = _evidence_by_type(
        [_geo_rule_evidence(), _transactions([_tx("1", out=True, amount=5.0, src_country="UK", dst_country="UAE")])]
    )
    signals = _observed_signals(grouped)
    assert signals["jurisdiction_signal"] is True
    assert signals["cross_border_flow"] is True


def test_a_graph_lookup_that_found_nothing_reads_as_checked_not_as_missing():
    """ "Đã tra cứu, không thấy" và "chưa tra cứu" dẫn tới hai hành động khác nhau."""
    from src.investigation.agents import _evidence_by_type, _observed_signals

    empty = evidence(
        EvidenceType.GRAPH_PATTERN,
        {"available": False, "missing_reason": "Bộ phát hiện đồ thị không ghi nhận mẫu hình nào"},
        source="graph_detector",
    )
    signals = _observed_signals(_evidence_by_type([empty]))
    assert signals["network_flow"] is False
    assert "network_flow" in signals  # có mặt = đã kiểm tra


def test_repeated_transaction_lookups_do_not_duplicate_the_same_facts():
    """Tác tử gọi GetTransactions hai lần thì giao dịch không được kể hai lần."""
    agent = ExplanationAgent(FakeGeminiService(), "INV-1")
    page = [_tx("16017462", out=True, amount=30101.17), _tx("16695722", out=False, amount=9257.95)]
    explanation = agent._deterministic(
        alert("mega_pna"),
        [risk_evidence("graph"), _behavior(incoming=1, outgoing=1), _transactions(page), _transactions(page)],
    )
    cited = [claim.claim for claim in explanation.claims if "mã giao dịch 16017462" in claim.claim]
    assert len(cited) == 1


def test_the_identifier_mask_never_eats_a_number_the_claim_must_prove():
    """``next_cursor`` là chuỗi "50", và nó từng cắt 5016.80 thành 16.80.

    Bộ quét số sau đó đi tìm 16,8 trong bằng chứng, không thấy, rồi đánh trượt
    một câu hoàn toàn đúng. Đo trên 163 phiên: đây là nguyên nhân
    UNSUPPORTED_CLAIM nhiều nhất.
    """
    from src.investigation.agents import _mask_identifiers

    page = _transactions([_tx("27571046", out=True, amount=5016.80)])
    page.payload["next_cursor"] = "50"
    masked = _mask_identifiers("tài khoản chuyển 5016.80 UK pounds (mã giao dịch 27571046).", [page])
    assert "5016.80" in masked


def test_critic_objection_about_a_transaction_id_in_the_ledger_is_refuted():
    """Sổ bằng chứng là bên nói lời cuối, kể cả với mã giao dịch."""
    page = _transactions([_tx("26005546", out=True, amount=21198.23)])
    page.integrity.source_record_ids = ["26005546"]
    issue = ValidationIssue(
        type="UNSUPPORTED_CLAIM",
        claim="Ngày 2023-06-08, tài khoản chuyển 21198.23 UK pounds (mã giao dịch 26005546).",
        detail="Giao dịch 26005546 không có trong danh mục evidence_index.",
    )
    explanation = Explanation(
        summary="x",
        risk_drivers=[],
        claims=[],
        facts=[],
        inferences=[],
        missing_information=[],
        typologies=[],
        confidence=0.9,
        recommended_action="ESCALATE_TO_L2",
        requires_human_review=True,
    )
    assert EvidenceCriticAgent._is_refuted(issue, explanation, [page]) is True


@pytest.mark.asyncio
async def test_critic_still_rejects_an_invented_count_when_the_ledger_is_complete():
    """Luật cắt-ngắn KHÔNG được nới cho hồ sơ có bằng chứng đầy đủ.

    Đây là vế chặn của bài kiểm dưới: nếu bỏ điều kiện "đã tự khai bị cắt" thì
    mọi phép đếm bịa đều lọt, và bộ kiểm tất định mất tác dụng với đúng loại
    sai sót nó sinh ra để bắt.
    """
    risk = risk_evidence("rule")
    explanation = Explanation(
        summary="Review required",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="Tài khoản thực hiện 999 giao dịch xuyên biên giới.",
                claim_type="FACT",
                evidence_refs=[risk.evidence_id],
                confidence=1,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[],  # KHÔNG khai bị cắt ngắn
        typologies=[],
        confidence=0.8,
        recommended_action="REQUEST_MORE_INFORMATION",
    )
    agent = EvidenceCriticAgent(MagicMock(), FakeGeminiService(), "INV-1")
    result = (await agent.validate(explanation, [risk])).output
    assert result.status == "FAIL"


@pytest.mark.asyncio
async def test_critic_excuses_a_count_dispute_when_the_ledger_was_truncated():
    """Sổ giao dịch bị cắt thì phép đếm KHÔNG BÊN NÀO kiểm chứng được.

    Hồ sơ thật: bản giải thích tự khai "Chỉ trích xuất được 50 giao dịch đầu
    tiên" rồi nói "15 giao dịch xuyên biên giới". Tác tử phản biện đếm trên đúng
    50 dòng ấy và phản đối — vòng 2 bảo có 17, vòng 3 bảo chỉ có 12. Ba con số
    cho cùng một câu hỏi, vì cả ba cùng đếm trên một sổ đã bị cắt. Đứng trên
    khiếu nại ấy để đánh trượt là buộc tội bịa đặt trong khi cả hai phía cùng mù.
    """
    risk = risk_evidence("rule")
    explanation = Explanation(
        summary="Review required",
        risk_drivers=[],
        claims=[
            Claim(
                claim_id="CLM-1",
                claim="Giao dịch đi qua hành lang UK → Morocco (15 giao dịch xuyên biên giới).",
                claim_type="FACT",
                evidence_refs=[risk.evidence_id],
                confidence=1,
            )
        ],
        facts=[],
        inferences=[],
        missing_information=[
            "Chỉ trích xuất được 50 giao dịch đầu tiên; tài khoản còn giao dịch chưa "
            "được đưa vào bằng chứng."
        ],
        typologies=[],
        confidence=0.8,
        recommended_action="REQUEST_MORE_INFORMATION",
    )
    agent = EvidenceCriticAgent(MagicMock(), FakeGeminiService(), "INV-1")
    result = (await agent.validate(explanation, [risk])).output
    assert result.status == "PASS", [i.detail for i in result.issues]


def test_prose_scrubber_removes_internal_codes_and_denominators():
    """Sửa khuôn mẫu tất định là chưa đủ — mô hình tự viết phần tóm tắt.

    Đo trên 30 phiên thật: bản tóm tắt Gemini viết ra câu "dựa trên mô hình phân
    tích mạng lưới giao dịch (mega_pna) với mức điểm rủi ro tối đa là 100/100",
    vừa lộ mã nhánh vừa dính lại đúng mẫu số đã bỏ khỏi khuôn mẫu. Đây là bộ lọc
    tất định ở đầu ra, không phải một câu nhắc trong prompt.
    """
    out = ExplanationAgent._scrub_prose(
        "dựa trên mô hình phân tích mạng lưới giao dịch (mega_pna) "
        "với mức điểm rủi ro tối đa là 100/100"
    )
    assert "mega_pna" not in out
    assert "100/100" not in out
    assert "100 điểm" in out


def test_prose_scrubber_keeps_machine_keys_and_long_numbers():
    """`source` là khoá tra nhãn, không phải câu chữ — đổi nó là làm hỏng phép tra.

    Và số tiền dài không được đụng tới: "906271514968" không phải điểm số.
    """
    tree = ExplanationAgent._scrub_tree(
        {"source": "mega_pna", "reason": "nhánh mega_pna là nguồn điểm",
         "facts": ["Tổng 906271514968 trên các giao dịch bị gắn cờ"]}
    )
    assert tree["source"] == "mega_pna"
    assert "mega_pna" not in tree["reason"]
    assert "906271514968" in tree["facts"][0]


# --- Nhấn mạnh đúng chiều đo của từng nhóm hành vi ---------------------------


def _typology(code: str, name_vi: str, required: list[str], supporting: list[str]) -> EvidenceEnvelope:
    labels = {
        "fan_in": "nhiều nguồn dồn vào",
        "fan_out": "phân tán ra nhiều đích",
        "short_dwell_time": "tiền nằm lại rất ngắn",
        "rapid_outflow": "chuyển đi ngay sau khi nhận",
        "network_flow": "tiền đi qua tài khoản",
        "value_retention": "giữ lại rất ít",
        "new_counterparties": "đối tác mới",
    }
    return evidence(
        EvidenceType.TYPOLOGY_MAPPING,
        {
            "typology_code": code,
            "name": code,
            "name_vi": name_vi,
            "description_vi": f"Mô tả của {name_vi}.",
            "required_signals": required,
            "supporting_signals": supporting,
            "signal_labels_vi": labels,
            "version": "v1",
        },
        source="typology_registry",
    )


def _narrative(
    code: str,
    name_vi: str,
    required: list[str],
    supporting: list[str],
    *,
    observed_overrides: dict | None = None,
) -> str:
    explanation = ExplanationAgent._deterministic(
        alert("ml"),
        [
            risk_evidence("ml"),
            behavior_evidence(**(observed_overrides or {})),
            _typology(code, name_vi, required, supporting),
        ],
    )
    return explanation.summary + " " + " ".join(explanation.inferences)


def test_dau_hieu_da_khop_phai_kem_so_do_khong_chi_ten():
    """"Khớp 3 trong 3 dấu hiệu" mà không có số là một câu rỗng.

    Chuyên viên đọc để biết bao nhiêu nguồn, bao nhiêu đích, nằm lại bao lâu —
    kèm ngưỡng để tự thấy nó vượt bao xa.
    """
    text = _narrative("T04", "Gom vào rồi toả ra bất thường", ["fan_in", "fan_out"], ["short_dwell_time"])

    assert "6 đối tác gửi" in text and "8 đối tác nhận" in text
    assert "ngưỡng ≥ 5" in text  # FAN_COUNTERPARTIES đi kèm ngay sau số đo


def test_moi_nhom_hanh_vi_nhan_manh_mot_chieu_do_khac_nhau():
    """Cùng một tài khoản, hai nhóm hành vi phải được kể theo hai chiều khác nhau."""
    fan = _narrative("T04", "Gom vào rồi toả ra bất thường", ["fan_in", "fan_out"], ["short_dwell_time"])
    speed = _narrative("T05", "Luân chuyển tiền tốc độ cao", ["rapid_outflow"], ["short_dwell_time"])

    # Nhóm gom–toả: nhấn SỐ LƯỢNG đầu vào/đầu ra.
    assert "số lượng nguồn dồn vào và số đích toả ra" in fan
    assert "6 đối tác gửi" in fan and "8 đối tác nhận" in fan

    # Nhóm luân chuyển nhanh: nhấn THỜI GIAN, và nêu tiền nằm lại bao lâu.
    assert "tốc độ" in speed
    assert "1.2 giờ" in speed and "93% tiền ra đi nhanh" in speed
    # Chiều đo của nhóm kia không được chiếm chỗ câu nhấn mạnh của nhóm này.
    assert "số lượng nguồn dồn vào" not in speed


def test_nhom_trung_chuyen_neu_ro_ty_le_tien_di_qua():
    text = _narrative(
        "T02", "Mạng lưới tài khoản trung chuyển", ["network_flow"], ["rapid_outflow", "new_counterparties"]
    )
    assert "vai trò trung chuyển" in text
    # 39900.25 / 41000.50 ≈ 97% số tiền NHẬN ĐƯỢC đã đi tiếp
    assert "97% số tiền nhận được đã đi tiếp" in text


def test_ty_le_tien_di_qua_khong_vuot_100_phan_tram():
    """Tài khoản chuyển đi nhiều hơn số nhận trong cửa sổ không thành "811%".

    Phần chênh đến từ tiền vào TRƯỚC cửa sổ; một tỉ lệ "đi qua" vượt 100% không
    có nghĩa nào, và đó là con số đã lọt ra bản giải thích thật trên production.
    """
    text = _narrative(
        "T02",
        "Mạng lưới tài khoản trung chuyển",
        ["network_flow"],
        ["rapid_outflow"],
        observed_overrides={"inflow_amount": 32920.87, "outflow_amount": 266894.95},
    )
    assert "100% số tiền nhận được đã đi tiếp" in text
    assert "chênh do tiền vào trước cửa sổ" in text
    assert "811" not in text


def test_cau_tom_tat_mang_theo_so_do_quyet_dinh():
    """Số quan trọng nhất phải nằm ở đoạn đầu, không bắt người đọc lần xuống dưới."""
    explanation = ExplanationAgent._deterministic(
        alert("ml"),
        [
            risk_evidence("ml"),
            behavior_evidence(),
            _typology("T05", "Luân chuyển tiền tốc độ cao", ["rapid_outflow"], ["short_dwell_time"]),
        ],
    )
    assert "1.2 giờ" in explanation.summary


def test_nhan_bang_chung_co_dau_tach_hang_nghin_van_che_duoc_cau():
    """Chuẩn hoá dấu tách phải áp cho CẢ câu lẫn bằng chứng.

    Nhãn yếu tố trong cơ sở dữ liệu nay là "Tổng 9 294 trên các giao dịch bị gắn
    cờ" (dấu cách mảnh). Câu diễn giải chép lại nhãn ấy; bộ kiểm bỏ dấu tách ở
    câu rồi so với bằng chứng còn nguyên dấu — hai chuỗi không bằng nhau, nhãn
    không che được câu, và con số trong nhãn bị đòi bằng chứng số học. Đo trên
    bản chạy lại 27/08/2026: đánh trượt 100% số phiên của hai lô liên tiếp.
    """
    label = "Tổng 9 294 trên các giao dịch bị gắn cờ, cộng thô theo nguyên tệ (chưa quy đổi)"
    rule = evidence(
        EvidenceType.RULE_TRIGGER,
        {"triggered_rules": [{"factor_code": "MP_FLAGGED_AMOUNT", "factor_label": label,
                              "contribution": "0.00", "weight": "0.00"}]},
        source="mega_pna_engine",
    )
    explanation = Explanation(
        summary="thử", risk_drivers=[], facts=[label + "."], inferences=[], missing_information=[],
        typologies=[], confidence=0.5, recommended_action="REQUEST_MORE_INFORMATION", requires_human_review=True,
        claims=[Claim(claim_id="C1", claim=label + ".", claim_type="FACT",
                      evidence_refs=[rule.evidence_id], confidence=1.0)],
    )
    critic = EvidenceCriticAgent.__new__(EvidenceCriticAgent)
    result = critic._deterministic_validate(explanation, [rule])

    assert result.status == "PASS", [i.detail for i in result.issues]


def test_so_co_dau_cach_thuong_van_kiem_chung_duoc():
    """Mô hình diễn đạt lại thường đổi dấu cách mảnh thành dấu cách thường.

    "5 155.25 Euro" khi ấy bị đọc thành hai số 5 và 155,25 — không số nào có
    trong bằng chứng — và một câu hoàn toàn đúng bị đánh trượt UNSUPPORTED_CLAIM.
    Đo trên bản chạy lại 27/08/2026: 3 trong 4 lỗi còn lại là do đúng chuyện này.
    """
    behaviour = evidence(
        EvidenceType.BEHAVIOR_FEATURE,
        {"observed": {"inflow_amount": 5155.25, "outflow_amount": 0.0, "incoming_count": 1,
                      "outgoing_count": 0, "unique_in_counterparties": 1, "unique_out_counterparties": 0,
                      "new_counterparties": 0, "rapid_outflow_percent": 0.0, "rapid_outflow_amount": 0.0,
                      "rapid_window_hours": 2, "median_dwell_hours": None, "active_days": 1,
                      "window_start": "2022-08-15T00:00:00Z", "window_end": "2022-09-14T00:00:00Z",
                      "window_days": 30, "currency": "Euro", "largest_amount": 5155.25}},
        source="feature_service",
    )
    claim_text = "Tài khoản nhận 5 155.25 Euro trong cửa sổ."  # dấu cách THƯỜNG
    explanation = Explanation(
        summary="thử", risk_drivers=[], facts=[claim_text], inferences=[], missing_information=[],
        typologies=[], confidence=0.5, recommended_action="REQUEST_MORE_INFORMATION", requires_human_review=True,
        claims=[Claim(claim_id="C1", claim=claim_text, claim_type="FACT",
                      evidence_refs=[behaviour.evidence_id], confidence=1.0)],
    )
    critic = EvidenceCriticAgent.__new__(EvidenceCriticAgent)

    assert critic._deterministic_validate(explanation, [behaviour]).status == "PASS"


def test_so_trong_nhan_yeu_to_duoc_tach_thanh_gia_tri_kiem_chung_duoc():
    """Số chỉ nằm trong chuỗi nhãn thì mọi cách diễn đạt lại đều làm nó mất kiểm chứng."""
    from src.investigation.tools import _label_numbers

    assert _label_numbers("Tổng 14 983 trên các giao dịch bị gắn cờ") == [14983.0]
    assert _label_numbers("0 giao dịch tiền mặt") == [0.0]


def test_ten_kenh_thanh_toan_doc_duoc_va_hop_nhat_hai_bo_du_lieu() -> None:
    """Câu dữ kiện phải đọc lên được, và hai bộ dữ liệu phải kể giống nhau.

    IBM ghi ``CREDIT_CARD``, SAML-D ghi ``Credit card``; nếu đưa thẳng vào câu
    thì cùng một hành vi lại hiện hai kiểu, và cả hai kiểu đều là mã máy.
    """
    from src.investigation.agents import _channel

    assert _channel("CREDIT_CARD") == _channel("Credit card") == "thẻ tín dụng"
    assert _channel("Cash Withdrawal") == "rút tiền mặt"
    assert _channel("Cross-border") == "chuyển tiền quốc tế"


def test_kenh_la_thi_giu_nguyen_chu_khong_doan() -> None:
    """Nạp thêm một bộ dữ liệu mới không được làm câu dữ kiện nói sai."""
    from src.investigation.agents import _channel

    assert _channel("SEPA_INSTANT") == "SEPA_INSTANT"
    assert _channel(None) == "không rõ"
