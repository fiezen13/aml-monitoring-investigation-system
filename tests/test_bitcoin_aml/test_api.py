"""Kiểm tra API suy luận Bitcoin AML qua ASGI thật.

Ghép bộ suy luận đã huấn luyện trên fixture vào router bằng monkeypatch, để test
không phụ thuộc artifact trên đĩa hay dataset thật.
"""

from __future__ import annotations

import pytest

from src.bitcoin_aml.inference import BitcoinAmlPredictor, ModelNotTrainedError
from src.bitcoin_aml.training import train_pipeline


@pytest.fixture
def trained_predictor(elliptic_shaped):
    train_pipeline(elliptic_shaped)
    return BitcoinAmlPredictor(elliptic_shaped)


@pytest.mark.asyncio
async def test_predict_returns_agent_evidence(client, monkeypatch, trained_predictor):
    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", lambda: trained_predictor)
    n = trained_predictor.feature_count
    body = {"transaction_id": "tx-api", "features": [0.2] * n, "timestep": 7}
    resp = await client.post("/api/v1/aml/bitcoin/predict", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detector"] == "bitcoin_aml"
    assert data["domain"] == "bitcoin"
    assert 0.0 <= data["prediction"]["risk_score"] <= 1.0
    assert data["decision"]["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert data["evidence"]["top_features"]


@pytest.mark.asyncio
async def test_predict_rejects_wrong_feature_count(client, monkeypatch, trained_predictor):
    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", lambda: trained_predictor)
    resp = await client.post("/api/v1/aml/bitcoin/predict", json={"transaction_id": "tx", "features": [0.1, 0.2]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_malformed_input_is_422(client, monkeypatch, trained_predictor):
    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", lambda: trained_predictor)
    resp = await client.post("/api/v1/aml/bitcoin/predict", json={"transaction_id": "tx"})  # thiếu features
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_prediction(client, monkeypatch, trained_predictor):
    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", lambda: trained_predictor)
    n = trained_predictor.feature_count
    body = {"transactions": [{"transaction_id": f"tx{i}", "features": [float(i)] * n} for i in range(4)]}
    resp = await client.post("/api/v1/aml/bitcoin/predict/batch", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 4
    assert len(data["results"]) == 4


@pytest.mark.asyncio
async def test_service_unavailable_when_model_not_trained(client, monkeypatch):
    def _raise():
        raise ModelNotTrainedError("chưa huấn luyện")

    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", _raise)
    n_body = {"transaction_id": "tx", "features": [0.1, 0.2, 0.3]}
    resp = await client.post("/api/v1/aml/bitcoin/predict", json=n_body)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_agent_adapter_receives_full_bitcoin_schema(client, monkeypatch, trained_predictor):
    """Bằng chứng cho tác tử phải đủ trường của lược đồ Bitcoin AML."""
    monkeypatch.setattr("src.api.bitcoin_routes.get_predictor", lambda: trained_predictor)
    n = trained_predictor.feature_count
    resp = await client.post("/api/v1/aml/bitcoin/predict", json={"transaction_id": "tx-agent", "features": [0.5] * n})
    data = resp.json()
    # Đủ ba khối tác tử cần: prediction / evidence / decision, cùng định danh nhánh.
    assert set(data) >= {
        "detector",
        "domain",
        "dataset",
        "model",
        "model_id",
        "entity_type",
        "transaction_id",
        "prediction",
        "evidence",
        "decision",
    }
    assert set(data["prediction"]) >= {"label", "risk_score", "confidence"}
    assert set(data["decision"]) >= {"risk_level", "requires_review"}
