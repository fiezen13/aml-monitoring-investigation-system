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
        {"alert_id": "ALT-1", "final_risk_score": 0.96, "fusion_available": False, "components": components},
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

    assert "41000.50" in facts and "39900.25" in facts
    assert "6 đối tác" in facts and "8 đối tác" in facts
    assert "92.73" in facts and "2 giờ" in facts
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
