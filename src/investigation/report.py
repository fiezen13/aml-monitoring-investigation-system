from __future__ import annotations

from src.investigation.schemas import EvidenceEnvelope, EvidenceType, Explanation, InvestigationPackage


def build_case_package(
    investigation_id: str,
    account_key: str,
    risk: dict,
    explanation: Explanation,
    evidence: list[EvidenceEnvelope],
) -> InvestigationPackage:
    """Deterministic formatter; it creates no new findings or claims."""
    behavior = [
        claim.claim
        for claim in explanation.claims
        if any(
            item.evidence_id in claim.evidence_refs
            and item.type in {EvidenceType.BEHAVIOR_FEATURE, EvidenceType.ANOMALY_EXPLANATION}
            for item in evidence
        )
    ]
    graph = [
        claim.claim
        for claim in explanation.claims
        if any(
            item.evidence_id in claim.evidence_refs
            and item.type in {EvidenceType.GRAPH_PATTERN, EvidenceType.GRAPH_NEIGHBORHOOD}
            for item in evidence
        )
    ]
    rules = [
        claim.claim
        for claim in explanation.claims
        if any(item.evidence_id in claim.evidence_refs and item.type == EvidenceType.RULE_TRIGGER for item in evidence)
    ]
    return InvestigationPackage(
        investigation_id=investigation_id,
        account=account_key,
        risk=risk,
        executive_summary=explanation.summary,
        primary_risk_drivers=explanation.risk_drivers,
        behavior_findings=behavior,
        graph_findings=graph,
        rule_findings=rules,
        typologies=explanation.typologies,
        evidence_refs=sorted({reference for claim in explanation.claims for reference in claim.evidence_refs}),
        missing_information=explanation.missing_information,
        recommended_next_step=explanation.recommended_action,
        requires_human_review=True,
    )
