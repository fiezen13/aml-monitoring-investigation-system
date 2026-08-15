from __future__ import annotations

import numpy as np

from src.fusion.training import choose_champion, parse_temporal_splits, select_fusion_weights


def test_mature_temporal_splits_are_half_open_and_ordered() -> None:
    splits = parse_temporal_splits(
        {
            "train": {"start": "2022-09-08T00:00:00Z", "end": "2022-09-11T00:00:00Z"},
            "val": {"start": "2022-09-11T00:00:00Z", "end": "2022-09-14T00:00:00Z"},
            "test": {"start": "2022-09-14T00:00:00Z", "end": "2022-09-18T00:00:00Z"},
        }
    )

    assert splits["train"].end == splits["val"].start
    assert splits["val"].end == splits["test"].start


def test_fusion_weight_search_never_drops_a_component() -> None:
    labels = np.array([0, 0, 0, 0, 1, 1], dtype=np.uint8)
    graph = np.array([0.1, 0.2, 0.3, 0.4, 0.8, 0.9])
    isolation_forest = np.array([0.9, 0.8, 0.7, 0.6, 0.2, 0.1])

    weights, report = select_fusion_weights(
        if_percentile=isolation_forest,
        graph_percentile=graph,
        labels=labels,
        minimum_component_weight=0.1,
        step=0.1,
        alert_budget_rate=1.0,
    )

    assert weights["graph"] > weights["isolation_forest"]
    assert min(weights.values()) >= 0.1
    assert report["selected"]["f1"] > 0


def test_champion_selection_uses_validation_only() -> None:
    champion = choose_champion(
        {
            "graph": {"f1": 0.10, "pr_auc": 0.20, "precision_at_k": 0.30},
            "fusion": {"f1": 0.11, "pr_auc": 0.19, "precision_at_k": 0.25},
        }
    )

    assert champion == "fusion"
