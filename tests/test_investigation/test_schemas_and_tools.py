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


def _tools_with_snapshot(features):
    """InvestigationTools với một ảnh chụp đặc trưng giả lập (hoặc không có)."""
    from unittest.mock import MagicMock

    from src.investigation.tools import InvestigationTools

    session = MagicMock()
    row = None if features is None else {"snapshot_id": "SNP-1", "model_version": "fusion-v2", "features": features}
    session.execute.return_value.mappings.return_value.first.return_value = row
    repository = MagicMock()
    repository.get.return_value = MagicMock(alert_id="ALT-1", account_key="001:A")
    return InvestigationTools(session, repository, "INV-1")


def _fusion_features(champion="fusion"):
    """Đúng bộ khoá mà scripts/load_fusion_release.py ghi vào snapshot."""
    return {
        "isolation_forest_percentile": 0.80,
        "graph_percentile": 0.60,
        # contribution = weight × percentile, xem src/fusion/model.py
        "isolation_forest_contribution": 0.40,
        "graph_contribution": 0.30,
        "champion": champion,
    }


def test_risk_breakdown_reports_real_branches_when_a_fusion_release_covers_the_alert():
    tools = _tools_with_snapshot(_fusion_features())
    components, fusion_available, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="ml", score=0.70, as_of_time="2022-09-27T14:22:00Z"
    )

    assert fusion_available is True
    assert components["anomaly"].score == 0.80
    assert components["graph"].score == 0.60
    # Trọng số suy ngược từ contribution / percentile.
    assert components["anomaly"].weight == 0.5
    assert components["graph"].weight == 0.5
    assert components["anomaly"].available and components["graph"].available
    # Ảnh chụp hai nhánh (không có khoá rule) thì nhánh rule báo không khả dụng.
    assert components["rule"].available is False
    assert limitation and "anomaly, graph" in limitation


def test_risk_breakdown_reports_all_three_branches_when_the_snapshot_has_them():
    """Bản hợp nhất ba nhánh — hộp 5 của sơ đồ kiến trúc."""
    features = _fusion_features()
    features.update({"rule_percentile": 0.9, "rule_contribution": 0.45})
    tools = _tools_with_snapshot(features)
    components, fusion_available, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="graph", score=0.70, as_of_time="2022-09-17T00:00:00Z"
    )

    assert fusion_available is True
    assert components["rule"].available is True
    assert components["rule"].score == 0.9
    assert components["rule"].weight == 0.5
    assert limitation and "rule" in limitation


def test_a_branch_with_zero_weight_is_reported_as_evaluated_not_omitted():
    """Trọng số 0 nghĩa là nhánh đã được cân nhắc rồi bị loại, khác với không chạy."""
    features = _fusion_features()
    features.update({"rule_percentile": 0.9, "rule_contribution": 0.0})
    tools = _tools_with_snapshot(features)
    _, _, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="graph", score=0.70, as_of_time="2022-09-17T00:00:00Z"
    )

    assert limitation and "bị loại ở bước kiểm định" in limitation


def test_risk_breakdown_names_the_single_champion_instead_of_claiming_fusion():
    """Có chạy hợp nhất nhưng một nhánh đơn thắng — không được báo fusion_available."""
    tools = _tools_with_snapshot(_fusion_features(champion="graph"))
    components, fusion_available, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="graph", score=0.70, as_of_time="2022-09-27T14:22:00Z"
    )

    assert fusion_available is False
    assert components["graph"].available is True
    assert components["anomaly"].available is False
    assert limitation and "thắng ở bước kiểm định" in limitation


def test_risk_breakdown_falls_back_to_the_detector_score_without_a_fusion_release():
    tools = _tools_with_snapshot(None)
    components, fusion_available, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="ml", score=1.0, as_of_time="2022-09-27T14:22:00Z"
    )

    assert fusion_available is False
    assert components["anomaly"].contribution == 1.0
    assert components["graph"].available is False
    assert limitation and "không phải được suy đoán" in limitation


def test_every_declared_detector_maps_to_a_scoring_branch():
    """Nhánh mới phải có mặt ở CẢ hai bảng, nếu không điểm rơi vào hư không.

    Bảng ánh xạ detector→nhánh và tuple các nhánh được khai báo tách rời nhau.
    Thêm nhánh mà chỉ sửa một trong hai thì cảnh báo vẫn chạy, vẫn có điểm, mà
    phần phân rã ghi mọi nhánh đều không khả dụng — sai lặng lẽ, không ai thấy.
    """
    tools = _tools_with_snapshot(None)
    for detector, branch in (
        ("rule", "rule"),
        ("ml", "anomaly"),
        ("graph", "graph"),
        ("mega_pna", "mega_pna"),
        ("geo_rule", "geo_rule"),
    ):
        components, _, _ = tools._risk_components(
            alert_id="ALT-1", account_key="001:A", detector=detector, score=0.8, as_of_time="2022-09-27T14:22:00Z"
        )
        assert branch in components, f"{detector} không có nhánh điểm tương ứng"
        assert components[branch].available is True, f"{detector} không gán được điểm vào {branch}"
        assert components[branch].contribution == 0.8
        assert components[branch].score == 0.8


def test_a_snapshot_without_the_full_fusion_key_set_is_not_treated_as_fusion():
    """Ảnh chụp đặc trưng thường (không có hợp nhất) không được đọc nhầm."""
    tools = _tools_with_snapshot({"rapid_outflow_ratio": 0.6})
    _, fusion_available, limitation = tools._risk_components(
        alert_id="ALT-1", account_key="001:A", detector="ml", score=1.0, as_of_time="2022-09-27T14:22:00Z"
    )

    assert fusion_available is False
    assert limitation and "Không có bản hợp nhất điểm" in limitation


def test_a_branch_with_zero_percentile_does_not_divide_by_zero():
    tools = _tools_with_snapshot(None)
    branch = tools._branch(0.0, 0.0, "snapshot:SNP-1")

    assert branch.weight == 0.0
    assert branch.available is False
    assert branch.source_ref is None
