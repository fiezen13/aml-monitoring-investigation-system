from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import numpy as np
import pandas as pd

from scripts.build_fusion_release import canonical_if_sql, select_fusion_weights


def test_canonical_if_prefers_split_and_aligns_timestamp(tmp_path) -> None:
    as_of = datetime(2022, 9, 7, 23, 59, 59, tzinfo=UTC)
    train = pd.DataFrame([{"account_key": "A", "as_of_ts": as_of, "f1": 1.0, "f2": 10.0}])
    val = pd.DataFrame([{"account_key": "A", "as_of_ts": as_of, "f1": 2.0, "f2": 20.0}])
    test = pd.DataFrame(columns=train.columns)
    scores = pd.DataFrame(
        [
            {
                "account_key": "A",
                "as_of_ts": as_of,
                "f1": 1.0,
                "f2": 10.0,
                "anomaly_score": 0.2,
                "model_version": "if-v1",
            },
            {
                "account_key": "A",
                "as_of_ts": as_of,
                "f1": 2.0,
                "f2": 20.0,
                "anomaly_score": 0.8,
                "model_version": "if-v1",
            },
        ]
    )
    graph = pd.DataFrame(
        [
            {
                "account_key": "A",
                "as_of_ts": datetime(2022, 9, 8, tzinfo=UTC),
                "sample_split": "val",
                "graph_score": 0.5,
            }
        ]
    )
    paths = {}
    for name, frame in {
        "isolation_forest_train_features": train,
        "isolation_forest_val_features": val,
        "isolation_forest_test_features": test,
        "isolation_forest_scores": scores,
        "graph_scores": graph,
    }.items():
        path = tmp_path / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        paths[name] = {"path": str(path)}
    config = {"artifacts": paths}

    connection = duckdb.connect()
    row = connection.execute(canonical_if_sql(config, ["f1", "f2"])).fetchone()
    connection.close()

    assert row[0] == "A"
    assert row[1] == datetime(2022, 9, 8, tzinfo=UTC)
    assert row[2] == "val"
    assert row[3] == 0.8


def test_weight_selection_keeps_both_components_nonzero() -> None:
    labels = np.array([0, 0, 0, 1, 1], dtype=np.uint8)
    graph = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    isolation_forest = np.array([0.9, 0.8, 0.7, 0.2, 0.1])

    weights, report = select_fusion_weights(
        if_percentile=isolation_forest,
        graph_percentile=graph,
        fusion_complete=np.ones(5, dtype=bool),
        labels=labels,
        minimum_component_weight=0.1,
        step=0.1,
        alert_budget_rate=1.0,
    )

    assert weights["graph"] > weights["isolation_forest"]
    assert weights["isolation_forest"] >= 0.1
    assert weights["graph"] >= 0.1
    assert report["selected"]["f1"] > 0
