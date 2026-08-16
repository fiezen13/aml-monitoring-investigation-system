import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    # Phải báo đúng tầng tác tử đang chạy, không phải tên khung mẫu.
    assert body["runtime"] == "fin07.investigation.workflow"
    assert body["agents"] == [
        "investigation_supervisor",
        "explanation_agent",
        "evidence_critic",
    ]
    assert body["max_agent_iterations"] >= 1
