"""Reviewed helpers for the canonical FIN-07 fusion-v2 training protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score

from src.models.graph_baseline import select_threshold_on_validation


@dataclass(frozen=True)
class TemporalSplit:
    """One half-open UTC snapshot range."""

    name: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.name not in {"train", "val", "test"}:
            raise ValueError(f"unsupported split name: {self.name}")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("split timestamps must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("split start must be before end")


def parse_temporal_splits(payload: dict[str, dict[str, str]]) -> dict[str, TemporalSplit]:
    """Parse, normalize and validate train/val/test ranges from release config."""

    if set(payload) != {"train", "val", "test"}:
        raise ValueError("snapshot_splits must contain exactly train, val and test")
    splits: dict[str, TemporalSplit] = {}
    for name in ("train", "val", "test"):
        start = datetime.fromisoformat(payload[name]["start"].replace("Z", "+00:00")).astimezone(UTC)
        end = datetime.fromisoformat(payload[name]["end"].replace("Z", "+00:00")).astimezone(UTC)
        splits[name] = TemporalSplit(name, start, end)
    if splits["train"].end > splits["val"].start or splits["val"].end > splits["test"].start:
        raise ValueError("snapshot splits overlap")
    return splits


def select_fusion_weights(
    *,
    if_percentile: np.ndarray,
    graph_percentile: np.ndarray,
    labels: np.ndarray,
    minimum_component_weight: float,
    step: float,
    alert_budget_rate: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Select non-zero fusion weights on validation only."""

    if not 0 < minimum_component_weight < 0.5:
        raise ValueError("minimum_component_weight must be in (0, 0.5)")
    if not 0 < step <= 0.5:
        raise ValueError("step must be in (0, 0.5]")
    if len(if_percentile) != len(graph_percentile) or len(labels) != len(if_percentile):
        raise ValueError("validation arrays must have equal length")
    if not np.isfinite(if_percentile).all() or not np.isfinite(graph_percentile).all():
        raise ValueError("fusion-v2 requires both component scores for every validation row")

    candidates: list[dict[str, Any]] = []
    values = np.arange(minimum_component_weight, 1.0 - minimum_component_weight + step / 2, step)
    for if_weight_raw in values:
        if_weight = round(float(if_weight_raw), 10)
        graph_weight = round(1.0 - if_weight, 10)
        scores = if_weight * if_percentile + graph_weight * graph_percentile
        threshold = select_threshold_on_validation(labels, scores, max_alert_rate=alert_budget_rate)
        candidates.append(
            {
                "isolation_forest_weight": if_weight,
                "graph_weight": graph_weight,
                "pr_auc": float(average_precision_score(labels, scores)),
                **threshold,
            }
        )

    selected = max(
        candidates,
        key=lambda item: (
            float(item["f1"]),
            float(item["pr_auc"]),
            float(item["precision"]),
            -abs(float(item["isolation_forest_weight"]) - 0.5),
        ),
    )
    weights = {
        "isolation_forest": float(selected["isolation_forest_weight"]),
        "graph": float(selected["graph_weight"]),
    }
    return weights, {
        "method": "validation_grid_max_f1_within_alert_budget",
        "minimum_component_weight": minimum_component_weight,
        "step": step,
        "selected": selected,
        "candidates": candidates,
    }


def choose_champion(validation_metrics: dict[str, dict[str, float | int]]) -> str:
    """Choose deployment champion without looking at test metrics."""

    allowed = {"graph", "fusion"}
    if set(validation_metrics) != allowed:
        raise ValueError(f"champion candidates must be {sorted(allowed)}")
    return max(
        ("graph", "fusion"),
        key=lambda name: (
            float(validation_metrics[name]["f1"]),
            float(validation_metrics[name]["pr_auc"]),
            float(validation_metrics[name]["precision_at_k"]),
            name == "graph",  # prefer the simpler model on an exact tie
        ),
    )
