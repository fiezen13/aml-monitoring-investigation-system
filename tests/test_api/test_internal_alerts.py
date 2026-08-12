"""Tests for internal IF alert ingest endpoint (validation)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_internal_alert_requires_three_reasons():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/internal/alerts",
            json={
                "account_key": "9:TESTACC001",
                "risk_score": 88.5,
                "reasons": [
                    {"factor_code": "a", "factor_label": "A", "contribution": 50},
                    {"factor_code": "b", "factor_label": "B", "contribution": 50},
                ],
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_alert_rejects_bad_account_key_format():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/internal/alerts",
            json={
                "account_key": "BADKEY",
                "risk_score": 70,
                "reasons": [
                    {"factor_code": "a", "factor_label": "A", "contribution": 40},
                    {"factor_code": "b", "factor_label": "B", "contribution": 30},
                    {"factor_code": "c", "factor_label": "C", "contribution": 30},
                ],
            },
        )
    assert response.status_code in (422, 500)
