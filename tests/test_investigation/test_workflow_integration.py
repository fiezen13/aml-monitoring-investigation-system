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


def test_rule_alert_runs_supervisor_explanation_critic_to_pass(db_engine):
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


def test_graph_alert_without_detector_evidence_stops_at_configured_limits(db_engine):
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
        assert state.iteration == settings.max_agent_iterations
        assert state.tool_call_count <= settings.max_tool_calls
        assert state.validation is not None and state.validation.status == "FAIL"
        assert any(issue.required_tool == "GetGraphEvidence" for issue in state.validation.issues)


def test_anomaly_alert_collects_deterministic_feature_attribution(db_engine):
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
