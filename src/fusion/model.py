"""Portable two-component model bundle for FIN-07 score fusion.

The project deliberately keeps Isolation Forest and Graph as independent
detectors.  This module packages both frozen estimators, their train-only
percentile calibrations and the explainable weighted fusion policy into one
release artifact.  It does not train an opaque end-to-end replacement model.
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.exceptions import InconsistentVersionWarning

FUSION_BUNDLE_FORMAT = "fin07.if_graph_fusion.joblib.v1"
REQUIRED_IF_KEYS = {"model", "scaler", "feature_cols", "window"}
REQUIRED_BUNDLE_KEYS = {
    "artifact_format",
    "fusion_version",
    "window",
    "weights",
    "isolation_forest",
    "graph",
    "calibrations",
    "threshold",
    "runtime",
    "provenance",
}


@dataclass(frozen=True)
class PercentileCalibration:
    """Monotone train-only score-to-percentile mapping."""

    score_knots: np.ndarray
    percentiles: np.ndarray

    def __post_init__(self) -> None:
        scores = np.asarray(self.score_knots, dtype=np.float64)
        percentiles = np.asarray(self.percentiles, dtype=np.float64)
        if scores.ndim != 1 or percentiles.ndim != 1 or len(scores) != len(percentiles):
            raise ValueError("calibration arrays must be one-dimensional and equally sized")
        if len(scores) < 2:
            raise ValueError("calibration requires at least two score knots")
        if not np.isfinite(scores).all() or not np.isfinite(percentiles).all():
            raise ValueError("calibration contains non-finite values")
        if np.any(np.diff(scores) <= 0) or np.any(np.diff(percentiles) < 0):
            raise ValueError("calibration must be strictly increasing by score and monotone by percentile")
        if percentiles[0] < 0 or percentiles[-1] > 1:
            raise ValueError("calibration percentiles must be in [0, 1]")
        object.__setattr__(self, "score_knots", scores)
        object.__setattr__(self, "percentiles", percentiles)

    def transform(self, scores: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, dtype=np.float64)
        return np.interp(
            values,
            self.score_knots,
            self.percentiles,
            left=0.0,
            right=1.0,
        )

    def to_payload(self) -> dict[str, np.ndarray]:
        return {
            "score_knots": self.score_knots,
            "percentiles": self.percentiles,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PercentileCalibration:
        return cls(
            score_knots=np.asarray(payload["score_knots"], dtype=np.float64),
            percentiles=np.asarray(payload["percentiles"], dtype=np.float64),
        )


def fit_percentile_calibration(
    train_scores: np.ndarray,
    *,
    quantile_count: int = 4097,
) -> PercentileCalibration:
    """Fit a compact empirical-CDF approximation from train scores only."""
    scores = np.asarray(train_scores, dtype=np.float64)
    scores = scores[np.isfinite(scores)]
    if scores.size < 2:
        raise ValueError("at least two finite train scores are required")
    if quantile_count < 3:
        raise ValueError("quantile_count must be >= 3")

    quantiles = np.linspace(0.0, 1.0, quantile_count, dtype=np.float64)
    values = np.quantile(scores, quantiles, method="linear")
    unique_values, first_indices, counts = np.unique(
        values,
        return_index=True,
        return_counts=True,
    )
    # Equal-score groups use their upper empirical percentile (CDF semantics).
    upper_indices = first_indices + counts - 1
    unique_percentiles = quantiles[upper_indices]
    if unique_values.size == 1:
        epsilon = np.finfo(np.float64).eps * max(abs(float(unique_values[0])), 1.0)
        unique_values = np.array([unique_values[0] - epsilon, unique_values[0] + epsilon])
        unique_percentiles = np.array([0.0, 1.0])
    return PercentileCalibration(unique_values, unique_percentiles)


def _load_joblib(path: str | Path) -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InconsistentVersionWarning)
        return joblib.load(path)


def load_graph_model_compat(path: str | Path) -> Any:
    """Load Hiển's sklearn 1.7 artifact and repair its legacy Cython module path.

    The handed pickle records ``_loss.CyHalfBinomialLoss`` while current
    scikit-learn exposes that extension as ``sklearn._loss._loss``.  The alias
    exists only for the duration of deserialization; a newly saved fusion
    bundle no longer needs it.
    """
    try:
        return _load_joblib(path)
    except ModuleNotFoundError as exc:
        if exc.name != "_loss":
            raise

    import sklearn._loss._loss as cy_loss

    previous = sys.modules.get("_loss")
    sys.modules["_loss"] = cy_loss
    try:
        return _load_joblib(path)
    finally:
        if previous is None:
            sys.modules.pop("_loss", None)
        else:
            sys.modules["_loss"] = previous


def _validate_if_artifact(artifact: Any) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("Isolation Forest artifact must be a dictionary")
    missing = REQUIRED_IF_KEYS - set(artifact)
    if missing:
        raise ValueError(f"Isolation Forest artifact missing keys: {sorted(missing)}")
    if len(artifact["feature_cols"]) != 20:
        raise ValueError("Isolation Forest artifact must declare exactly 20 features")
    if str(artifact["window"]) != "7d":
        raise ValueError("fusion release only accepts the frozen 7d Isolation Forest")
    return artifact


def isolation_forest_scores(artifact: dict[str, Any], features: np.ndarray) -> np.ndarray:
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != len(artifact["feature_cols"]):
        raise ValueError("Isolation Forest feature matrix has the wrong shape")
    raw = -np.asarray(artifact["model"].decision_function(matrix), dtype=np.float64)
    scaled = artifact["scaler"].transform(raw.reshape(-1, 1)).ravel()
    return np.clip(scaled, 0.0, 1.0)


def graph_scores(model: Any, features: np.ndarray, expected_features: int) -> np.ndarray:
    matrix = np.asarray(features, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != expected_features:
        raise ValueError("Graph feature matrix has the wrong shape")
    return np.asarray(model.predict_proba(matrix)[:, 1], dtype=np.float64)


def build_fusion_bundle(
    *,
    fusion_version: str,
    isolation_forest_artifact: dict[str, Any],
    graph_model: Any,
    graph_feature_cols: list[str],
    if_calibration: PercentileCalibration,
    graph_calibration: PercentileCalibration,
    weights: dict[str, float],
    threshold: float,
    provenance: dict[str, Any],
    graph_model_version: str = "graph_histgb_hien_v1",
) -> dict[str, Any]:
    if_artifact = dict(_validate_if_artifact(isolation_forest_artifact))
    if_artifact.setdefault("model_version", "if_behavior_7d_huong_v1")
    if len(graph_feature_cols) != int(getattr(graph_model, "n_features_in_", -1)):
        raise ValueError("Graph model feature count does not match its declared feature contract")
    if set(weights) != {"isolation_forest", "graph"}:
        raise ValueError("fusion weights must contain isolation_forest and graph")
    if any(float(value) <= 0 for value in weights.values()):
        raise ValueError("fusion weights must be positive")
    weight_total = float(sum(weights.values()))
    normalized_weights = {key: float(value) / weight_total for key, value in weights.items()}
    if not 0 <= threshold <= 1:
        raise ValueError("fusion threshold must be in [0, 1]")

    return {
        "artifact_format": FUSION_BUNDLE_FORMAT,
        "fusion_version": fusion_version,
        "window": "7d",
        "score_semantics": "train-percentile weighted score; 1.0 = highest review priority",
        "missing_component_policy": "renormalize_available_weights",
        "weights": normalized_weights,
        "threshold": float(threshold),
        "isolation_forest": if_artifact,
        "graph": {
            "model": graph_model,
            "model_version": graph_model_version,
            "feature_cols": list(graph_feature_cols),
        },
        "calibrations": {
            "isolation_forest": if_calibration.to_payload(),
            "graph": graph_calibration.to_payload(),
        },
        "runtime": {
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
        },
        "provenance": provenance,
    }


def save_fusion_bundle(bundle: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output, compress=3)
    return output


def load_fusion_bundle(path: str | Path, *, require_runtime_match: bool = True) -> dict[str, Any]:
    bundle = _load_joblib(path)
    if not isinstance(bundle, dict):
        raise ValueError("fusion bundle must be a dictionary")
    missing = REQUIRED_BUNDLE_KEYS - set(bundle)
    if missing:
        raise ValueError(f"fusion bundle missing keys: {sorted(missing)}")
    if bundle["artifact_format"] != FUSION_BUNDLE_FORMAT:
        raise ValueError(f"unsupported fusion bundle format: {bundle['artifact_format']!r}")
    expected = str(bundle["runtime"].get("scikit_learn"))
    if require_runtime_match and expected != sklearn.__version__:
        raise RuntimeError(f"fusion bundle requires scikit-learn {expected}; running {sklearn.__version__}")
    _validate_if_artifact(bundle["isolation_forest"])
    PercentileCalibration.from_payload(bundle["calibrations"]["isolation_forest"])
    PercentileCalibration.from_payload(bundle["calibrations"]["graph"])
    return bundle


def predict_fusion(
    bundle: dict[str, Any],
    *,
    isolation_forest_features: np.ndarray | None,
    graph_features: np.ndarray | None,
) -> dict[str, np.ndarray]:
    """Score one aligned batch and retain each component's contribution."""
    if isolation_forest_features is None and graph_features is None:
        raise ValueError("at least one detector feature matrix is required")

    if_raw: np.ndarray | None = None
    graph_raw: np.ndarray | None = None
    if isolation_forest_features is not None:
        if_raw = isolation_forest_scores(bundle["isolation_forest"], isolation_forest_features)
    if graph_features is not None:
        graph_raw = graph_scores(
            bundle["graph"]["model"],
            graph_features,
            len(bundle["graph"]["feature_cols"]),
        )

    lengths = {len(item) for item in (if_raw, graph_raw) if item is not None}
    if len(lengths) != 1:
        raise ValueError("component feature matrices must contain the same number of rows")
    size = lengths.pop()
    if_percentile = np.full(size, np.nan, dtype=np.float64)
    graph_percentile = np.full(size, np.nan, dtype=np.float64)
    if if_raw is not None:
        if_percentile = PercentileCalibration.from_payload(bundle["calibrations"]["isolation_forest"]).transform(if_raw)
    if graph_raw is not None:
        graph_percentile = PercentileCalibration.from_payload(bundle["calibrations"]["graph"]).transform(graph_raw)

    if_weight = float(bundle["weights"]["isolation_forest"])
    graph_weight = float(bundle["weights"]["graph"])
    available_weight = np.where(np.isfinite(if_percentile), if_weight, 0.0) + np.where(
        np.isfinite(graph_percentile), graph_weight, 0.0
    )
    if_contribution = np.where(
        np.isfinite(if_percentile),
        if_weight * if_percentile / available_weight,
        0.0,
    )
    graph_contribution = np.where(
        np.isfinite(graph_percentile),
        graph_weight * graph_percentile / available_weight,
        0.0,
    )
    risk_score = np.clip(if_contribution + graph_contribution, 0.0, 1.0)
    return {
        "isolation_forest_raw_score": if_raw if if_raw is not None else np.full(size, np.nan),
        "graph_raw_score": graph_raw if graph_raw is not None else np.full(size, np.nan),
        "isolation_forest_percentile": if_percentile,
        "graph_percentile": graph_percentile,
        "isolation_forest_contribution": if_contribution,
        "graph_contribution": graph_contribution,
        "risk_score": risk_score,
        "triggered": risk_score >= float(bundle["threshold"]),
    }
