"""Tests for Isolation Forest → aml.detection.result.v1 mapping."""

from __future__ import annotations

from datetime import UTC, datetime

from src.services.if_detection_result import (
    build_detection_result,
    reason_code_from_feature,
    stable_result_id,
    validate_detection_result,
)


def _sample_row(**overrides):
    row = {
        "account_key": "70:10042B660",
        "as_of_ts": datetime(2022, 9, 6, 23, 59, 59, tzinfo=UTC),
        "window": "7d",
        "anomaly_score": 0.812345,
        "model_version": "if_baseline_7d_v1",
        "top_anomalous_features": (
            '[{"feature": "txn_per_active_day", "value": 12.0, "percentile": 99},'
            ' {"feature": "rapid_outflow_ratio", "value": 0.9, "percentile": 97},'
            ' {"feature": "new_counterparty_ratio", "value": 0.8, "percentile": 95}]'
        ),
    }
    row.update(overrides)
    return row


def test_reason_code_is_upper_snake() -> None:
    assert reason_code_from_feature("txn_per_active_day") == "TXN_PER_ACTIVE_DAY"
    assert reason_code_from_feature("ab") == "IF_AB"


def test_stable_result_id_is_deterministic() -> None:
    as_of = datetime(2022, 9, 6, 23, 59, 59, tzinfo=UTC)
    a = stable_result_id("70:10042B660", as_of, "7d", "if_baseline_7d_v1")
    b = stable_result_id("70:10042B660", as_of, "7d", "if_baseline_7d_v1")
    assert a == b
    assert a.startswith("DR-IF-")


def test_build_payload_passes_contract() -> None:
    payload = build_detection_result(
        _sample_row(),
        threshold=0.7,
        evaluated_at=datetime(2026, 8, 12, 3, 0, 0, tzinfo=UTC),
    )
    assert payload["detector"]["detector_type"] == "ML_UNSUPERVISED"
    assert payload["triggered"] is True
    assert 0.0 <= payload["score"] <= 1.0
    assert payload["confidence"] < 1.0
    assert len(payload["reason_codes"]) >= 1
    errors = validate_detection_result(payload)
    assert errors == [], errors


def test_below_threshold_still_emitted_as_not_triggered() -> None:
    payload = build_detection_result(_sample_row(anomaly_score=0.2), threshold=0.7)
    assert payload["triggered"] is False
    assert payload["score"] == 0.2
    assert validate_detection_result(payload) == []


def test_missing_top_features_gets_fallback_reason() -> None:
    payload = build_detection_result(_sample_row(top_anomalous_features="[]"))
    assert payload["reason_codes"][0]["code"] == "IF_ANOMALY_SCORE"
    assert validate_detection_result(payload) == []
