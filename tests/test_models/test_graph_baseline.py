from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.models.graph_baseline import (
    DETECTOR_FEATURE_COLUMNS,
    MODELING_SCHEMA_VERSION,
    build_modeling_table,
)


def _feature(account: str, as_of: str) -> dict:
    return {
        "account_key": account,
        "as_of_ts": pd.Timestamp(as_of),
        "snapshot_date": pd.Timestamp(as_of).date(),
        "window": "7d",
        "sample_split": "val",
        "feature_schema_version": "graph_features_v1",
        "in_degree_7d": 1,
        "out_degree_7d": 1,
        "unique_neighbors_7d": 2,
        "in_out_degree_ratio_7d": 1.0,
        "new_in_counterparty_ratio_7d": 0.5,
        "new_out_counterparty_ratio_7d": 0.5,
        "inflow_concentration_7d": 1.0,
        "outflow_dispersion_7d": 1.0,
        "history_available": 1,
        "history_days_observed": 7,
    }


def test_current_window_target_boundaries_and_detector_aggregation(tmp_path: Path) -> None:
    as_of = "2022-09-09T00:00:00Z"
    features = pd.DataFrame([_feature(a, as_of) for a in "ABCDEFGH"])
    feature_path = tmp_path / "features.parquet"
    features.to_parquet(feature_path, index=False)

    detections = pd.DataFrame(
        [
            {
                "account_key": "A",
                "as_of_ts": pd.Timestamp(as_of),
                "detected_pattern": "FAN_IN",
                "pattern_instance_id": "fan-1",
                "cycle_length": None,
            },
            {
                "account_key": "A",
                "as_of_ts": pd.Timestamp(as_of),
                "detected_pattern": "CYCLE",
                "pattern_instance_id": "cycle-1",
                "cycle_length": 3,
            },
            {
                "account_key": "A",
                "as_of_ts": pd.Timestamp(as_of),
                "detected_pattern": "CYCLE",
                "pattern_instance_id": "cycle-2",
                "cycle_length": 6,
            },
        ]
    )
    detection_path = tmp_path / "detections.parquet"
    detections.to_parquet(detection_path, index=False)

    db_path = tmp_path / "tx.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("SET TimeZone='Asia/Ho_Chi_Minh'")
    con.execute(
        """
        CREATE TABLE transaction(
          transaction_id VARCHAR,
          occurred_at TIMESTAMPTZ,
          from_account_key VARCHAR,
          to_account_key VARCHAR,
          label_laundering UTINYINT
        )
        """
    )
    con.executemany(
        "INSERT INTO transaction VALUES (?, ?::TIMESTAMPTZ, ?, ?, ?)",
        [
            ("at-start", "2022-09-02T00:00:00Z", "A", "B", 1),
            ("inside", "2022-09-08T23:59:59Z", "C", "D", 1),
            ("before-start", "2022-09-01T23:59:59Z", "E", "F", 1),
            ("at-end", "2022-09-09T00:00:00Z", "G", "A", 1),
            ("after-end", "2022-09-09T00:00:01Z", "H", "A", 1),
        ],
    )
    con.close()

    output_path = tmp_path / "modeling.parquet"
    meta = build_modeling_table(db_path, feature_path, detection_path, output_path)
    result = pd.read_parquet(output_path).set_index("account_key")

    assert meta["modeling_schema_version"] == MODELING_SCHEMA_VERSION
    assert set(result.index[result["target_laundering"] == 1]) == {"A", "B", "C", "D"}
    assert result.loc["A", "fan_in_hit"] == 1
    assert result.loc["A", "cycle_hit"] == 1
    assert result.loc["A", "cycle_motif_count"] == 2
    assert result.loc["A", "cycle_length_min"] == 3
    assert result.loc["A", "cycle_length_max"] == 6
    assert result.loc["A", "detector_motif_count"] == 3
    assert (result.loc[["B", "C"], DETECTOR_FEATURE_COLUMNS] == 0).all().all()
