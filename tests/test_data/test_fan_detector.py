"""Unit tests for FAN_IN / FAN_OUT detectors."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.data.fan_detector import (
    DETECTION_COLUMNS,
    compute_fan_auxiliary_duckdb,
    compute_fan_auxiliary_snapshot_duckdb,
    detect_fan_from_features,
    hydrate_fan_evidence,
    load_fan_config,
    run_fan_detector,
    run_fan_detector_batched,
    select_fan_v3_min_hits,
)
from src.data.schemas import assert_no_label_leakage

CFG = {
    "detector_version": "graph_fan_test",
    "fan_in": {
        "detected_pattern": "FAN_IN",
        "min_in_degree_7d": 10,
        "max_inflow_concentration_7d": 0.3,
    },
    "fan_out": {
        "detected_pattern": "FAN_OUT",
        "min_out_degree_7d": 10,
        "min_outflow_dispersion_7d": 0.5,
    },
}


def _feat(**kwargs) -> dict:
    base = {
        "account_key": "A",
        "as_of_ts": pd.Timestamp("2022-09-07T00:00:00Z"),
        "snapshot_date": pd.Timestamp("2022-09-06").date(),
        "window": "7d",
        "sample_split": "val",
        "in_degree_7d": 0,
        "out_degree_7d": 0,
        "inflow_concentration_7d": 1.0,
        "outflow_dispersion_7d": 0.0,
        "new_in_counterparty_ratio_7d": 1.0,
        "new_out_counterparty_ratio_7d": 1.0,
    }
    base.update(kwargs)
    return base


def test_fan_in_fires_on_degree_and_low_hhi() -> None:
    df = pd.DataFrame(
        [
            _feat(account_key="IN", in_degree_7d=10, inflow_concentration_7d=0.2),
            _feat(account_key="NO", in_degree_7d=10, inflow_concentration_7d=0.9),
            _feat(account_key="LO", in_degree_7d=5, inflow_concentration_7d=0.1),
        ]
    )
    det, ev = detect_fan_from_features(df, CFG)
    assert set(det["account_key"]) == {"IN"}
    assert (det["detected_pattern"] == "FAN_IN").all()
    assert len(ev) == 1
    assert ev[0]["accounts"] == ["IN"]
    assert ev[0]["metrics"]["in_degree_7d"] == 10


def test_fan_out_fires_on_degree_and_dispersion() -> None:
    df = pd.DataFrame(
        [
            _feat(account_key="OUT", out_degree_7d=10, outflow_dispersion_7d=0.6),
            _feat(account_key="NO", out_degree_7d=10, outflow_dispersion_7d=0.1),
        ]
    )
    det, ev = detect_fan_from_features(df, CFG)
    assert set(det["account_key"]) == {"OUT"}
    assert (det["detected_pattern"] == "FAN_OUT").all()
    assert len(ev) == 1


def test_both_patterns_same_account() -> None:
    df = pd.DataFrame(
        [
            _feat(
                account_key="BOTH",
                in_degree_7d=12,
                inflow_concentration_7d=0.2,
                out_degree_7d=15,
                outflow_dispersion_7d=0.7,
            )
        ]
    )
    det, ev = detect_fan_from_features(df, CFG)
    assert set(det["detected_pattern"]) == {"FAN_IN", "FAN_OUT"}
    assert det["pattern_instance_id"].nunique() == 2
    assert len(ev) == 2


def test_new_star_ignored_even_if_high() -> None:
    # High new_* alone must not fire
    df = pd.DataFrame(
        [
            _feat(
                account_key="N",
                in_degree_7d=2,
                inflow_concentration_7d=0.1,
                new_in_counterparty_ratio_7d=1.0,
            )
        ]
    )
    det, _ev = detect_fan_from_features(df, CFG)
    assert det.empty


def test_one_detection_per_center_motif() -> None:
    df = pd.DataFrame([_feat(account_key="C", in_degree_7d=10, inflow_concentration_7d=0.2)])
    det, ev = detect_fan_from_features(df, CFG)
    assert len(det) == 1
    assert len(ev) == 1
    assert det.iloc[0]["pattern_instance_id"] == ev[0]["pattern_instance_id"]
    assert det.iloc[0]["evidence_id"] == ev[0]["evidence_id"]


def test_split_filter() -> None:
    df = pd.DataFrame(
        [
            _feat(account_key="T", sample_split="train", in_degree_7d=10, inflow_concentration_7d=0.1),
            _feat(account_key="V", sample_split="val", in_degree_7d=10, inflow_concentration_7d=0.1),
            _feat(account_key="X", sample_split="test", in_degree_7d=10, inflow_concentration_7d=0.1),
        ]
    )
    det, _ = detect_fan_from_features(df, CFG, splits=["train", "val"])
    assert set(det["account_key"]) == {"T", "V"}


def test_no_label_columns_and_schema() -> None:
    df = pd.DataFrame([_feat(in_degree_7d=10, inflow_concentration_7d=0.1)])
    det, _ = detect_fan_from_features(df, CFG)
    assert_no_label_leakage(list(det.columns))
    assert list(det.columns) == list(DETECTION_COLUMNS)


def test_frozen_config_loads() -> None:
    cfg = load_fan_config()
    assert cfg["detector_version"] == "graph_fan_v3_min"
    assert cfg["supervised_model"] is False
    assert cfg["fan_in"]["rule_type"] == "two_of_four_points"
    assert cfg["fan_in"]["min_points"] == 2
    assert cfg["fan_out"]["rule_type"] == "degree_shape"


def test_v3_min_point_rule_and_simple_fan_out() -> None:
    cfg = load_fan_config()
    rows = pd.DataFrame(
        [
            {
                "account_key": "IN_HIT",
                "detected_pattern": "FAN_IN",
                "degree_7d": 6,
                "tx_count_7d": 5,
                "counterparty_day_concentration": 0.4,
                "shape_7d": 0.9,
            },
            {
                "account_key": "IN_ONE_POINT",
                "detected_pattern": "FAN_IN",
                "degree_7d": 6,
                "tx_count_7d": 5,
                "counterparty_day_concentration": 1.0,
                "shape_7d": 0.9,
            },
            {
                "account_key": "OUT_HIT",
                "detected_pattern": "FAN_OUT",
                "degree_7d": 5,
                "tx_count_7d": 5,
                "counterparty_day_concentration": 1.0,
                "shape_7d": 0.7,
            },
            {
                "account_key": "OUT_MISS",
                "detected_pattern": "FAN_OUT",
                "degree_7d": 4,
                "tx_count_7d": 100,
                "counterparty_day_concentration": 0.1,
                "shape_7d": 0.9,
            },
        ]
    )
    hits = select_fan_v3_min_hits(rows, cfg)
    assert set(hits["account_key"]) == {"IN_HIT", "OUT_HIT"}


def test_daily_snapshot_auxiliary_matches_transaction_join_oracle(tmp_path) -> None:
    features = pd.DataFrame(
        [
            _feat(
                account_key="C",
                as_of_ts=pd.Timestamp("2022-09-07T00:00:00Z"),
                snapshot_date=pd.Timestamp("2022-09-06").date(),
                in_degree_7d=2,
                out_degree_7d=2,
                inflow_concentration_7d=0.5,
                outflow_dispersion_7d=0.5,
            ),
            _feat(
                account_key="C",
                as_of_ts=pd.Timestamp("2022-09-08T00:00:00Z"),
                snapshot_date=pd.Timestamp("2022-09-07").date(),
                in_degree_7d=2,
                out_degree_7d=2,
                inflow_concentration_7d=0.5,
                outflow_dispersion_7d=0.5,
            ),
        ]
    )
    transactions = pd.DataFrame(
        [
            {
                "transaction_id": "i1",
                "occurred_at": pd.Timestamp("2022-09-01T01:00:00Z"),
                "from_account_key": "S1",
                "to_account_key": "C",
            },
            {
                "transaction_id": "i2",
                "occurred_at": pd.Timestamp("2022-09-01T02:00:00Z"),
                "from_account_key": "S1",
                "to_account_key": "C",
            },
            {
                "transaction_id": "i3",
                "occurred_at": pd.Timestamp("2022-09-02T01:00:00Z"),
                "from_account_key": "S2",
                "to_account_key": "C",
            },
            {
                "transaction_id": "o1",
                "occurred_at": pd.Timestamp("2022-09-03T01:00:00Z"),
                "from_account_key": "C",
                "to_account_key": "D1",
            },
            {
                "transaction_id": "o2",
                "occurred_at": pd.Timestamp("2022-09-03T02:00:00Z"),
                "from_account_key": "C",
                "to_account_key": "D2",
            },
        ]
    )
    feature_path = tmp_path / "features.parquet"
    db_path = tmp_path / "aml.duckdb"
    features.to_parquet(feature_path, index=False)
    con = duckdb.connect(str(db_path))
    con.register("tx_frame", transactions)
    con.execute("CREATE TABLE transaction AS SELECT * FROM tx_frame")
    con.close()

    oracle = compute_fan_auxiliary_duckdb(features, duckdb_path=db_path, min_degree=2)
    actual = pd.concat(
        [
            compute_fan_auxiliary_snapshot_duckdb(
                feature_path,
                duckdb_path=db_path,
                as_of_ts=as_of,
                min_degree=2,
            )
            for as_of in sorted(features["as_of_ts"].unique())
        ],
        ignore_index=True,
    )
    columns = list(oracle.columns)
    oracle = oracle.sort_values(["as_of_ts", "detected_pattern", "account_key"]).reset_index(drop=True)
    actual = actual.loc[:, columns].sort_values(["as_of_ts", "detected_pattern", "account_key"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, oracle, check_dtype=False)


def test_batched_fan_artifacts_match_full_join_oracle(tmp_path) -> None:
    features = pd.DataFrame(
        [
            _feat(
                account_key="CENTER",
                sample_split="train",
                in_degree_7d=6,
                out_degree_7d=5,
                inflow_concentration_7d=0.2,
                outflow_dispersion_7d=0.8,
            )
        ]
    )
    transactions = []
    for index in range(6):
        transactions.append(
            {
                "transaction_id": f"IN{index}",
                "occurred_at": pd.Timestamp("2022-09-02T00:00:00Z") + pd.Timedelta(hours=index),
                "from_account_key": f"S{index}",
                "to_account_key": "CENTER",
                "amount": float(index + 1),
                "amount_received": float(index + 1),
                "channel": "ACH",
            }
        )
    for index in range(5):
        transactions.append(
            {
                "transaction_id": f"OUT{index}",
                "occurred_at": pd.Timestamp("2022-09-03T00:00:00Z") + pd.Timedelta(hours=index),
                "from_account_key": "CENTER",
                "to_account_key": f"D{index}",
                "amount": float(index + 1),
                "amount_received": float(index + 1),
                "channel": "ACH",
            }
        )
    feature_path = tmp_path / "features.parquet"
    db_path = tmp_path / "aml.duckdb"
    detection_path = tmp_path / "detections.parquet"
    evidence_path = tmp_path / "evidence.jsonl"
    features.to_parquet(feature_path, index=False)
    con = duckdb.connect(str(db_path))
    con.register("tx_frame", pd.DataFrame(transactions))
    con.execute("CREATE TABLE transaction AS SELECT * FROM tx_frame")
    con.close()

    oracle_det, oracle_ev = run_fan_detector(
        features_path=feature_path,
        duckdb_path=db_path,
        splits=["train"],
    )
    summary = run_fan_detector_batched(
        features_path=feature_path,
        duckdb_path=db_path,
        detection_path=detection_path,
        evidence_path=evidence_path,
        splits=["train"],
    )
    actual_det = pd.read_parquet(detection_path)
    actual_ev = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    oracle_det["snapshot_date"] = pd.to_datetime(oracle_det["snapshot_date"]).dt.date
    assert actual_det["cycle_length"].isna().all()
    assert oracle_det["cycle_length"].isna().all()
    pd.testing.assert_frame_equal(
        actual_det.drop(columns="cycle_length"),
        oracle_det.drop(columns="cycle_length"),
        check_dtype=False,
    )
    assert json.dumps(actual_ev, sort_keys=True) == json.dumps(oracle_ev, sort_keys=True, default=str)
    assert summary["detection_rows"] == len(oracle_det)
    assert summary["evidence_rows"] == len(oracle_ev)


def test_determinism() -> None:
    df = pd.DataFrame(
        [
            _feat(account_key="A", in_degree_7d=11, inflow_concentration_7d=0.2),
            _feat(account_key="B", out_degree_7d=12, outflow_dispersion_7d=0.6),
        ]
    )
    d1, e1 = detect_fan_from_features(df, CFG)
    d2, e2 = detect_fan_from_features(df, CFG)
    pd.testing.assert_frame_equal(d1, d2)
    assert e1 == e2


def test_hydrates_traceable_fan_witnesses_per_counterparty() -> None:
    features = pd.DataFrame([_feat(account_key="CENTER", in_degree_7d=2, inflow_concentration_7d=0.2)])
    cfg = {**CFG, "fan_in": {**CFG["fan_in"], "min_in_degree_7d": 2}}
    detections, evidence = detect_fan_from_features(features, cfg)
    transactions = pd.DataFrame(
        [
            {
                "transaction_id": "OLD",
                "occurred_at": "2022-08-30T00:00:00Z",
                "from_account_key": "S1",
                "to_account_key": "CENTER",
                "amount": 99,
                "amount_received": 99,
            },
            {
                "transaction_id": "S1_SMALL",
                "occurred_at": "2022-09-02T00:00:00Z",
                "from_account_key": "S1",
                "to_account_key": "CENTER",
                "amount": 10,
                "amount_received": 10,
            },
            {
                "transaction_id": "S1_BIG",
                "occurred_at": "2022-09-03T00:00:00Z",
                "from_account_key": "S1",
                "to_account_key": "CENTER",
                "amount": 20,
                "amount_received": 20,
            },
            {
                "transaction_id": "S2",
                "occurred_at": "2022-09-06T23:59:59Z",
                "from_account_key": "S2",
                "to_account_key": "CENTER",
                "amount": 5,
                "amount_received": 5,
            },
            {
                "transaction_id": "FUTURE",
                "occurred_at": "2022-09-07T00:00:00Z",
                "from_account_key": "S3",
                "to_account_key": "CENTER",
                "amount": 100,
                "amount_received": 100,
            },
        ]
    )
    hydrated = hydrate_fan_evidence(detections, evidence, transactions=transactions)
    ev = hydrated[0]
    assert ev["transaction_ids"] == ["S1_BIG", "S2"]
    assert ev["witness_counterparty_count"] == 2
    assert ev["accounts"] == ["CENTER", "S1", "S2"]
    assert all(h["to_account_key"] == "CENTER" for h in ev["hops"])
    assert all(h["transaction_id"] not in {"OLD", "FUTURE"} for h in ev["hops"])


def test_hydrates_fan_out_in_correct_direction() -> None:
    features = pd.DataFrame([_feat(account_key="CENTER", out_degree_7d=1, outflow_dispersion_7d=0.6)])
    cfg = {**CFG, "fan_out": {**CFG["fan_out"], "min_out_degree_7d": 1}}
    detections, evidence = detect_fan_from_features(features, cfg)
    transactions = pd.DataFrame(
        [
            {
                "transaction_id": "OUT",
                "occurred_at": "2022-09-04T00:00:00Z",
                "from_account_key": "CENTER",
                "to_account_key": "D1",
                "amount": 7,
                "amount_received": 7,
            },
            {
                "transaction_id": "WRONG",
                "occurred_at": "2022-09-04T00:00:00Z",
                "from_account_key": "D1",
                "to_account_key": "CENTER",
                "amount": 8,
                "amount_received": 8,
            },
        ]
    )
    hydrated = hydrate_fan_evidence(detections, evidence, transactions=transactions)
    assert hydrated[0]["transaction_ids"] == ["OUT"]
    assert hydrated[0]["hops"][0]["from_account_key"] == "CENTER"
