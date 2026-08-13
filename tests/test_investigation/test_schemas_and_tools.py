from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.investigation.schemas import Claim, RiskComponent
from src.investigation.tools import NeighborhoodArgs, TransactionArgs, _behavior_from_rows


def test_fact_claim_requires_evidence_reference():
    with pytest.raises(ValidationError, match="cần ít nhất một tham chiếu bằng chứng"):
        Claim(claim_id="CLM-1", claim="A fact", claim_type="FACT", evidence_refs=[], confidence=1)


def test_inference_is_explicitly_allowed_without_reference_at_schema_boundary():
    claim = Claim(claim_id="CLM-2", claim="A labelled hypothesis", claim_type="INFERENCE", confidence=0.5)
    assert claim.claim_type == "INFERENCE"


def test_score_contribution_contract_uses_zero_to_one_scale():
    component = RiskComponent(score=0.8, weight=0.5, contribution=0.4)
    assert component.contribution == component.score * component.weight
    with pytest.raises(ValidationError):
        RiskComponent(score=80, weight=0.5, contribution=0.4)


def test_tool_arguments_enforce_hard_limits():
    with pytest.raises(ValidationError):
        TransactionArgs(account_key="001:A", limit=501)
    with pytest.raises(ValidationError):
        NeighborhoodArgs(account_key="001:A", hops=5)


def test_tool_router_rejects_non_allow_listed_request_with_audit_trace():
    from unittest.mock import MagicMock

    from src.investigation.tools import InvestigationTools

    repository = MagicMock()
    repository.get.return_value = MagicMock(alert_id="ALT-1", account_key="001:A")
    tools = InvestigationTools(MagicMock(), repository, "INV-1")
    with pytest.raises(ValueError, match="không nằm trong danh sách được phép"):
        tools.execute("execute_shell", {"command": "id"})
    repository.add_trace.assert_called_once()
    assert repository.add_trace.call_args.kwargs["event_type"] == "INVALID_TOOL_REQUEST"


def test_tool_router_rejects_cross_investigation_account():
    from unittest.mock import MagicMock

    from src.investigation.tools import InvestigationTools

    repository = MagicMock()
    repository.get.return_value = MagicMock(alert_id="ALT-1", account_key="001:A")
    tools = InvestigationTools(MagicMock(), repository, "INV-1")
    with pytest.raises(PermissionError, match="outside the current investigation"):
        tools.execute("GetAccountBehavior", {"account_key": "001:OTHER", "window": "7d"})
    assert repository.add_trace.call_args.kwargs["event_type"] == "INVALID_TOOL_REQUEST"


def test_behavior_features_are_deterministic_and_source_derived():
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    rows = [
        {
            "transaction_id": 1,
            "occurred_at": now,
            "from_account_key": "001:B",
            "to_account_key": "001:A",
            "amount": 100.0,
        },
        {
            "transaction_id": 2,
            "occurred_at": now + timedelta(hours=1),
            "from_account_key": "001:A",
            "to_account_key": "001:C",
            "amount": 80.0,
        },
    ]
    features = _behavior_from_rows("001:A", rows, [])
    assert features["txn_count"] == 2
    assert features["incoming_count"] == 1
    assert features["outgoing_count"] == 1
    assert features["rapid_outflow_ratio"] == 1.0
    assert features["median_dwell_time"] == 1.0
