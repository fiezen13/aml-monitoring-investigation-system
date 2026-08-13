"""Unit tests for Graph GT enrich + simple detector match eval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.data.graph_detector_eval import (
    compute_cycle_metrics,
    compute_split_metrics,
    match_cycle_detections_to_gt,
    match_detections_to_gt,
    window_overlaps_gt,
)
from src.data.graph_gt_enrich import (
    canonicalize_directed_cycle,
    derive_center,
    enrich_cycle_gt_for_graph_eval,
    enrich_ibm_gt_for_graph_eval,
)
from src.data.schemas import make_account_key


def test_make_account_key_strips_leading_zeros() -> None:
    assert make_account_key("0110", "8000A94C0") == "110:8000A94C0"
    assert make_account_key(110, "8000A94C0") == "110:8000A94C0"
    assert make_account_key("000", "ABC") == "0:ABC"


def test_derive_center_fan_and_gather() -> None:
    fan_in = [
        {"from_account_key": "A", "to_account_key": "C"},
        {"from_account_key": "B", "to_account_key": "C"},
    ]
    assert derive_center("FAN-IN", fan_in) == "C"
    fan_out = [
        {"from_account_key": "C", "to_account_key": "A"},
        {"from_account_key": "C", "to_account_key": "B"},
    ]
    assert derive_center("FAN-OUT", fan_out) == "C"
    gather = [
        {"from_account_key": "A", "to_account_key": "H"},
        {"from_account_key": "B", "to_account_key": "H"},
        {"from_account_key": "H", "to_account_key": "D"},
        {"from_account_key": "H", "to_account_key": "E"},
    ]
    assert derive_center("GATHER-SCATTER", gather) == "H"


def test_window_overlap() -> None:
    t_min = pd.Timestamp("2022-09-01T02:00:00Z")
    t_max = pd.Timestamp("2022-09-03T14:00:00Z")
    # snapshot_date 2022-09-06 → window [2022-08-31, 2022-09-07)
    assert window_overlaps_gt(snapshot_date=date(2022, 9, 6), t_min=t_min, t_max=t_max)
    # far later window
    assert not window_overlaps_gt(snapshot_date=date(2022, 9, 20), t_min=t_min, t_max=t_max)


def test_match_and_metrics_simple() -> None:
    gt = [
        {
            "instance_id": "g1",
            "detected_pattern": "FAN_IN",
            "center_account_key": "C",
            "t_min": "2022-09-01T02:00:00+00:00",
            "t_max": "2022-09-03T14:00:00+00:00",
            "sample_split": "test",
        },
        {
            "instance_id": "g2",
            "detected_pattern": "FAN_OUT",
            "center_account_key": "X",
            "t_min": "2022-09-01T00:00:00+00:00",
            "t_max": "2022-09-02T00:00:00+00:00",
            "sample_split": "test",
        },
    ]
    det = pd.DataFrame(
        [
            {
                "pattern_instance_id": "PI1",
                "account_key": "C",
                "detected_pattern": "FAN_IN",
                "snapshot_date": date(2022, 9, 6),
                "sample_split": "test",
                "as_of_ts": pd.Timestamp("2022-09-07T00:00:00Z"),
            },
            {
                "pattern_instance_id": "PI_FP",
                "account_key": "Z",
                "detected_pattern": "FAN_IN",
                "snapshot_date": date(2022, 9, 10),
                "sample_split": "test",
                "as_of_ts": pd.Timestamp("2022-09-11T00:00:00Z"),
            },
        ]
    )
    matches = match_detections_to_gt(det, gt)
    assert len(matches) == 1
    assert matches[0]["instance_id"] == "g1"
    m = compute_split_metrics(det, gt, matches, split="test")
    # FAN_IN: 1/1 recall, 1/2 precision; FAN_OUT: 0/1 recall, 0 pred
    assert m["by_pattern"]["FAN_IN"]["recall"] == 1.0
    assert m["by_pattern"]["FAN_IN"]["precision"] == 0.5
    assert m["overall"]["n_gt_hit"] == 1
    assert m["overall"]["n_pred_hit"] == 1


def test_enrich_real_patterns_smoke() -> None:
    path = Path("data/raw/ibm-aml/LI-Small_Patterns.txt")
    if not path.exists():
        return
    rows = enrich_ibm_gt_for_graph_eval(path)
    assert len(rows) == 12 + 19 + 12
    assert all(r["center_account_key"] for r in rows)
    # first FAN-IN center should match Task1 key (no leading zero bank)
    fan = next(r for r in rows if r["pattern_type"] == "FAN-IN")
    assert fan["center_account_key"] == "110:8000A94C0"
    assert "T" in fan["t_min"] or "+" in fan["t_min"]


def test_cycle_gt_enrich_excludes_unsupported_lengths() -> None:
    path = Path("data/raw/ibm-aml/LI-Small_Patterns.txt")
    if not path.exists():
        return
    result = enrich_cycle_gt_for_graph_eval(path)
    assert result["total_cycle_blocks"] == 12
    assert result["eligible_count"] == 6
    assert len(result["excluded"]) == 6
    assert all(item["reason"] == "cycle_length_exceeds_detector" for item in result["excluded"])


def test_cycle_matching_uses_directed_signature_and_window() -> None:
    assert canonicalize_directed_cycle(["B", "C", "A", "B"]) == ("A", "B", "C")
    gt = [
        {
            "instance_id": "g1",
            "cycle_signature": ["A", "B", "C"],
            "t_min": "2022-09-01T00:00:00Z",
            "t_max": "2022-09-02T00:00:00Z",
            "sample_split": "test",
        }
    ]
    evidence = [
        {
            "pattern_instance_id": "p1",
            "detected_pattern": "CYCLE",
            "accounts": ["A", "B", "C"],
            "snapshot_date": date(2022, 9, 5),
            "sample_split": "test",
        }
    ]
    matches = match_cycle_detections_to_gt(evidence, gt)
    assert len(matches) == 1
    metrics = compute_cycle_metrics(evidence, gt, matches, split="test")
    assert metrics["status"] == "EVALUATED"
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
