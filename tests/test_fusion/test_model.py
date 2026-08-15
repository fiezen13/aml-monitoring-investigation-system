from __future__ import annotations

import json

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.preprocessing import MinMaxScaler

from src.fusion.model import (
    FUSION_BUNDLE_FORMAT,
    build_fusion_bundle,
    fit_percentile_calibration,
    load_fusion_bundle,
    predict_fusion,
    save_fusion_bundle,
)


def _models():
    rng = np.random.default_rng(42)
    if_x = rng.normal(size=(80, 20))
    if_model = IsolationForest(n_estimators=5, random_state=42).fit(if_x)
    if_raw = -if_model.decision_function(if_x)
    scaler = MinMaxScaler().fit(if_raw.reshape(-1, 1))
    if_artifact = {
        "model": if_model,
        "scaler": scaler,
        "feature_cols": [f"if_{index}" for index in range(20)],
        "window": "7d",
        "model_version": "if-test-v1",
    }

    graph_x = rng.normal(size=(80, 18)).astype(np.float32)
    graph_y = np.array([0, 1] * 40, dtype=np.uint8)
    graph_model = HistGradientBoostingClassifier(
        max_iter=3,
        min_samples_leaf=2,
        random_state=42,
    ).fit(graph_x, graph_y)
    graph_raw = graph_model.predict_proba(graph_x)[:, 1]
    return if_x, if_raw, if_artifact, graph_x, graph_raw, graph_model


def test_percentile_calibration_is_monotone_and_bounded() -> None:
    calibration = fit_percentile_calibration(
        np.array([0.1, 0.1, 0.4, 0.9]),
        quantile_count=9,
    )
    transformed = calibration.transform(np.array([-1.0, 0.1, 0.4, 2.0]))

    assert np.all(np.diff(transformed) >= 0)
    assert transformed[0] == 0.0
    assert transformed[-1] == 1.0


def test_bundle_round_trip_and_explainable_contributions(tmp_path) -> None:
    if_x, if_raw, if_artifact, graph_x, graph_raw, graph_model = _models()
    bundle = build_fusion_bundle(
        fusion_version="fusion-test-v1",
        isolation_forest_artifact=if_artifact,
        graph_model=graph_model,
        graph_feature_cols=[f"graph_{index}" for index in range(18)],
        if_calibration=fit_percentile_calibration(if_raw, quantile_count=33),
        graph_calibration=fit_percentile_calibration(graph_raw, quantile_count=33),
        weights={"isolation_forest": 1.0, "graph": 1.0},
        threshold=0.7,
        provenance={"test": True},
    )
    path = save_fusion_bundle(bundle, tmp_path / "fusion.joblib")
    loaded = load_fusion_bundle(path)
    result = predict_fusion(
        loaded,
        isolation_forest_features=if_x[:8],
        graph_features=graph_x[:8],
    )

    assert loaded["artifact_format"] == FUSION_BUNDLE_FORMAT
    assert np.allclose(
        result["risk_score"],
        result["isolation_forest_contribution"] + result["graph_contribution"],
    )
    assert np.all((result["risk_score"] >= 0) & (result["risk_score"] <= 1))
    assert np.array_equal(result["triggered"], result["risk_score"] >= 0.7)


def test_missing_component_renormalizes_available_weight() -> None:
    if_x, if_raw, if_artifact, graph_x, graph_raw, graph_model = _models()
    bundle = build_fusion_bundle(
        fusion_version="fusion-test-v1",
        isolation_forest_artifact=if_artifact,
        graph_model=graph_model,
        graph_feature_cols=[f"graph_{index}" for index in range(18)],
        if_calibration=fit_percentile_calibration(if_raw, quantile_count=33),
        graph_calibration=fit_percentile_calibration(graph_raw, quantile_count=33),
        weights={"isolation_forest": 0.5, "graph": 0.5},
        threshold=0.7,
        provenance=json.loads("{}"),
    )
    result = predict_fusion(
        bundle,
        isolation_forest_features=None,
        graph_features=graph_x[:8],
    )

    assert np.all(result["isolation_forest_contribution"] == 0)
    assert np.allclose(result["risk_score"], result["graph_percentile"])
