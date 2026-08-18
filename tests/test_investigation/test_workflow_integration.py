import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.config import get_settings
from src.db.session import get_engine, get_session
from src.investigation.repository import InvestigationRepository
from src.investigation.workflow import InvestigationWorkflow
from src.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def db_engine():
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"PostgreSQL is unavailable: {exc}")
    return engine


def test_rule_alert_runs_supervisor_explanation_critic_to_pass(db_engine, disable_authz):
    with db_engine.begin() as connection:
        alert_id = connection.execute(
            text("SELECT alert_id FROM alert WHERE detector = 'rule' ORDER BY alert_id LIMIT 1")
        ).scalar_one_or_none()
    if not alert_id:
        pytest.skip("Current LI-Small batch has no rule alert")

    with get_session() as session:
        repository = InvestigationRepository(session)
        investigation = repository.create(alert_id, triggered_by="pytest")
        session.commit()

        asyncio.run(InvestigationWorkflow(session).run(investigation.investigation_id))
        session.commit()

        state = repository.get(investigation.investigation_id)
        assert state.status == "COMPLETED"
        assert state.validation is not None
        assert state.validation.status == "PASS"
        assert state.tool_call_count <= 8
        assert repository.latest_explanation(investigation.investigation_id) is not None
        event_types = [event.event_type for event in repository.list_trace(investigation.investigation_id)]
        assert "EXPLANATION_GENERATED" in event_types
        assert "VALIDATION_PASS" in event_types
        assert "HUMAN_REVIEW_REQUIRED" in event_types

        async def assert_api_contracts() -> None:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                base = f"/api/v1/investigations/{investigation.investigation_id}"
                assert (await client.get(base)).status_code == 200
                assert (await client.get(f"{base}/evidence")).json()
                assert (await client.get(f"{base}/trace")).json()
                explanation_response = await client.get(f"{base}/explanation")
                assert explanation_response.status_code == 200
                assert explanation_response.json()["requires_human_review"] is True
                assert (await client.get(f"{base}/package")).status_code == 200

        asyncio.run(assert_api_contracts())


def test_graph_alert_without_detector_evidence_stops_at_configured_limits(db_engine, disable_authz):
    with db_engine.begin() as connection:
        alert_id = connection.execute(
            text("SELECT alert_id FROM alert WHERE detector = 'graph' ORDER BY alert_id LIMIT 1")
        ).scalar_one_or_none()
    if not alert_id:
        pytest.skip("Current LI-Small batch has no graph alert")

    with get_session() as session:
        repository = InvestigationRepository(session)
        investigation = repository.create(alert_id, triggered_by="pytest")
        session.commit()
        asyncio.run(InvestigationWorkflow(session).run(investigation.investigation_id))
        session.commit()

        state = repository.get(investigation.investigation_id)
        settings = get_settings()
        assert state.status == "INSUFFICIENT_EVIDENCE"
        # Dừng ở MỘT trong hai trần cấu hình, không phải trần cụ thể nào.
        #
        # Trước khi có bước bổ sung bằng chứng bắt buộc, phiên này luôn cạn vòng
        # lặp trước. Nay quy trình tự gọi GetGraphEvidence, lượt gọi ấy tính vào
        # ngân sách công cụ, nên cảnh báo không có bằng chứng đồ thị chạm trần
        # công cụ sớm hơn một vòng. Cả hai đều là dừng đúng chỗ; khẳng định vào
        # đúng một trần là khoá chi tiết hiện thực chứ không khoá hành vi.
        assert state.iteration <= settings.max_agent_iterations
        assert state.tool_call_count <= settings.max_tool_calls
        assert state.iteration == settings.max_agent_iterations or state.tool_call_count == settings.max_tool_calls
        assert state.validation is not None and state.validation.status == "FAIL"
        assert any(issue.required_tool == "GetGraphEvidence" for issue in state.validation.issues)


def test_anomaly_alert_collects_deterministic_feature_attribution(db_engine, disable_authz):
    with db_engine.begin() as connection:
        alert_id = connection.execute(
            text("SELECT alert_id FROM alert WHERE detector = 'ml' ORDER BY alert_id LIMIT 1")
        ).scalar_one_or_none()
    if not alert_id:
        pytest.skip("Current LI-Small batch has no ML alert")

    with get_session() as session:
        repository = InvestigationRepository(session)
        investigation = repository.create(alert_id, triggered_by="pytest")
        session.commit()
        asyncio.run(InvestigationWorkflow(session).run(investigation.investigation_id))
        session.commit()

        state = repository.get(investigation.investigation_id)
        assert state.status == "COMPLETED"
        evidence_types = {item.type for item in repository.list_evidence(investigation.investigation_id)}
        assert "BEHAVIOR_FEATURE" in evidence_types
        assert "ANOMALY_EXPLANATION" in evidence_types


def _purge_investigation(session, investigation_id: str) -> None:
    """Xoá nhãn do test tạo ra.

    Kho nhãn là dữ liệu dùng để hiệu chỉnh ngưỡng; không dọn thì mỗi lần chạy
    test lại thêm một nhãn giả vào đó.

    Chỉ xoá được dòng nhãn: bản thân phiên điều tra kéo theo ``investigation_trace``
    vốn là bảng chỉ-ghi-thêm (trigger ``deny_mutation``), và đó là chủ ý — nhật ký
    điều tra không được phép xoá. Phiên điều tra của test nằm lại là chấp nhận
    được, đúng như các test tích hợp đã có.
    """
    session.execute(
        text("DELETE FROM review_feedback WHERE investigation_id = :id"),
        {"id": investigation_id},
    )


def test_a_human_review_produces_a_queryable_label(db_engine, disable_authz):
    """Vòng phản hồi phải để lại nhãn dùng được, không chỉ một dòng nhật ký.

    Trước đây quyết định rà soát chỉ vào ``investigation.human_review`` (bị ghi
    đè mỗi lần rà soát lại) và ``audit_log``. Cả hai đều không giữ điểm số tại
    thời điểm ra quyết định — mà thiếu điểm thì nhãn không hiệu chỉnh được cho
    cái gì.
    """
    with db_engine.begin() as connection:
        alert = (
            connection.execute(text("SELECT alert_id, risk_score, detector FROM alert ORDER BY alert_id LIMIT 1"))
            .mappings()
            .first()
        )
    if not alert:
        pytest.skip("Không có cảnh báo nào trong cơ sở dữ liệu")

    with get_session() as session:
        repository = InvestigationRepository(session)
        investigation = repository.create(alert["alert_id"], triggered_by="pytest")
        session.execute(
            text("UPDATE investigation SET status = 'COMPLETED' WHERE investigation_id = :id"),
            {"id": investigation.investigation_id},
        )
        session.commit()

        repository.review(
            investigation.investigation_id,
            user_id="U-001",
            decision="CLOSE_AS_LIKELY_FALSE_POSITIVE",
            reason="Kiểm tra tích hợp cho vòng phản hồi",
        )
        session.commit()

        feedback = (
            session.execute(
                text(
                    """SELECT decision, label, risk_score, detector, reviewed_by, investigation_status
                         FROM review_feedback WHERE investigation_id = :id"""
                ),
                {"id": investigation.investigation_id},
            )
            .mappings()
            .first()
        )
        # Kho nhãn là dữ liệu huấn luyện — không để nhãn của test nằm lại trong đó.
        _purge_investigation(session, investigation.investigation_id)
        session.commit()

    assert feedback is not None
    assert feedback["decision"] == "CLOSE_AS_LIKELY_FALSE_POSITIVE"
    assert feedback["label"] == "NOT_SUSPICIOUS"
    # Ảnh chụp điểm tại thời điểm quyết định — đây là phần khiến nhãn dùng được.
    assert float(feedback["risk_score"]) == float(alert["risk_score"])
    assert feedback["detector"] == alert["detector"]
    assert feedback["reviewed_by"] == "U-001"


def test_an_inconclusive_decision_is_not_labelled_as_a_false_positive(db_engine, disable_authz):
    """ "Cần thêm thông tin" không phải nhãn âm — chuyên viên chưa kết luận."""
    with db_engine.begin() as connection:
        alert_id = connection.execute(
            text("SELECT alert_id FROM alert ORDER BY alert_id DESC LIMIT 1")
        ).scalar_one_or_none()
    if not alert_id:
        pytest.skip("Không có cảnh báo nào trong cơ sở dữ liệu")

    with get_session() as session:
        repository = InvestigationRepository(session)
        investigation = repository.create(alert_id, triggered_by="pytest")
        session.execute(
            text("UPDATE investigation SET status = 'INSUFFICIENT_EVIDENCE' WHERE investigation_id = :id"),
            {"id": investigation.investigation_id},
        )
        session.commit()

        repository.review(
            investigation.investigation_id,
            user_id="U-001",
            decision="REQUEST_MORE_INFORMATION",
            reason="Kiểm tra tích hợp cho nhãn chưa kết luận",
        )
        session.commit()

        label = session.execute(
            text("SELECT label FROM review_feedback WHERE investigation_id = :id"),
            {"id": investigation.investigation_id},
        ).scalar_one()
        _purge_investigation(session, investigation.investigation_id)
        session.commit()

    assert label == "INCONCLUSIVE"
