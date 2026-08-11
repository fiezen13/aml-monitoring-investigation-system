"""Unit tests for GATHER_SCATTER median-based detector."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.data.gather_scatter_detector import (
    DETECTED_PATTERN,
    DETECTION_COLUMNS,
    detect_gather_scatter,
    load_gather_config,
)
from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import snapshot_window_bounds

CFG = {
    "detector_version": "graph_gather_test",
    "s_min": 3,
    "d_min": 3,
    "tolerance_hours": 0.0,
    "amount_ratio_lo": 0.2,
    "amount_ratio_hi": 5.0,
    "temporal_rule": "median_inbound_le_median_outbound_plus_tolerance",
}


def _feat(**kwargs) -> dict:
    base = {
        "account_key": "C",
        "as_of_ts": pd.Timestamp("2022-09-07T00:00:00Z"),
        "snapshot_date": date(2022, 9, 6),
        "window": "7d",
        "sample_split": "val",
        "in_degree_7d": 5,
        "out_degree_7d": 5,
        "new_in_counterparty_ratio_7d": 1.0,
        "new_out_counterparty_ratio_7d": 1.0,
    }
    base.update(kwargs)
    return base


def _tx_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _gather_then_scatter_txs(center: str = "C") -> pd.DataFrame:
    """3 early inbound CPs, then 3 late outbound CPs; ratio ~1."""
    start, _end = snapshot_window_bounds(date(2022, 9, 6))
    t0 = start + pd.Timedelta(hours=1)
    rows = []
    for i, src in enumerate(["S1", "S2", "S3"]):
        rows.append(
            {
                "transaction_id": f"IN{i}",
                "occurred_at": t0 + pd.Timedelta(hours=i),
                "from_account_key": src,
                "to_account_key": center,
                "amount": 100.0,
                "amount_received": 100.0,
            }
        )
    t1 = t0 + pd.Timedelta(hours=24)
    for i, dst in enumerate(["D1", "D2", "D3"]):
        rows.append(
            {
                "transaction_id": f"OUT{i}",
                "occurred_at": t1 + pd.Timedelta(hours=i),
                "from_account_key": center,
                "to_account_key": dst,
                "amount": 100.0,
                "amount_received": 100.0,
            }
        )
    return _tx_frame(rows)


def test_fires_when_median_in_before_median_out() -> None:
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    det, ev = detect_gather_scatter(feats, transactions=_gather_then_scatter_txs(), config=CFG)
    assert len(det) == 1
    assert det.iloc[0]["detected_pattern"] == DETECTED_PATTERN
    assert len(ev) == 1
    assert set(ev[0]["sources"]) == {"S1", "S2", "S3"}
    assert set(ev[0]["destinations"]) == {"D1", "D2", "D3"}
    assert ev[0]["metrics"]["amount_ratio"] == 1.0


def test_rejects_when_median_out_before_median_in() -> None:
    """Outbound mass earlier than inbound → fail temporal with tol=0."""
    start, _ = snapshot_window_bounds(date(2022, 9, 6))
    t_early = start + pd.Timedelta(hours=1)
    t_late = start + pd.Timedelta(hours=40)
    rows = []
    for i, dst in enumerate(["D1", "D2", "D3"]):
        rows.append(
            {
                "transaction_id": f"OUT{i}",
                "occurred_at": t_early + pd.Timedelta(hours=i),
                "from_account_key": "C",
                "to_account_key": dst,
                "amount": 100.0,
                "amount_received": 100.0,
            }
        )
    for i, src in enumerate(["S1", "S2", "S3"]):
        rows.append(
            {
                "transaction_id": f"IN{i}",
                "occurred_at": t_late + pd.Timedelta(hours=i),
                "from_account_key": src,
                "to_account_key": "C",
                "amount": 100.0,
                "amount_received": 100.0,
            }
        )
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    det, _ = detect_gather_scatter(feats, transactions=_tx_frame(rows), config=CFG)
    assert det.empty


def test_tolerance_allows_near_overlap() -> None:
    start, _ = snapshot_window_bounds(date(2022, 9, 6))
    # med_in slightly after med_out by ~6h → fail tol=0, pass tol=12
    rows = []
    for i, src in enumerate(["S1", "S2", "S3"]):
        rows.append(
            {
                "transaction_id": f"IN{i}",
                "occurred_at": start + pd.Timedelta(hours=20 + i),
                "from_account_key": src,
                "to_account_key": "C",
                "amount": 50.0,
                "amount_received": 50.0,
            }
        )
    for i, dst in enumerate(["D1", "D2", "D3"]):
        rows.append(
            {
                "transaction_id": f"OUT{i}",
                "occurred_at": start + pd.Timedelta(hours=10 + i),
                "from_account_key": "C",
                "to_account_key": dst,
                "amount": 50.0,
                "amount_received": 50.0,
            }
        )
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    tx = _tx_frame(rows)
    det0, _ = detect_gather_scatter(feats, transactions=tx, config=CFG)
    assert det0.empty
    cfg12 = {**CFG, "tolerance_hours": 12.0}
    det12, _ = detect_gather_scatter(feats, transactions=tx, config=cfg12)
    assert len(det12) == 1


def test_amount_ratio_bounds() -> None:
    start, _ = snapshot_window_bounds(date(2022, 9, 6))
    rows = []
    for i, src in enumerate(["S1", "S2", "S3"]):
        rows.append(
            {
                "transaction_id": f"IN{i}",
                "occurred_at": start + pd.Timedelta(hours=1 + i),
                "from_account_key": src,
                "to_account_key": "C",
                "amount": 100.0,
                "amount_received": 100.0,
            }
        )
    for i, dst in enumerate(["D1", "D2", "D3"]):
        rows.append(
            {
                "transaction_id": f"OUT{i}",
                "occurred_at": start + pd.Timedelta(hours=30 + i),
                "from_account_key": "C",
                "to_account_key": dst,
                "amount": 1000.0,  # ratio = 10 → outside [0.2, 5]
                "amount_received": 1000.0,
            }
        )
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    det, _ = detect_gather_scatter(feats, transactions=_tx_frame(rows), config=CFG)
    assert det.empty
    wide = {**CFG, "amount_ratio_hi": 10.0}
    det2, _ = detect_gather_scatter(feats, transactions=_tx_frame(rows), config=wide)
    assert len(det2) == 1


def test_degree_prefilter_skips_low_degree() -> None:
    feats = pd.DataFrame([_feat(in_degree_7d=2, out_degree_7d=5)])
    det, _ = detect_gather_scatter(feats, transactions=_gather_then_scatter_txs(), config=CFG)
    assert det.empty


def test_one_detection_per_center() -> None:
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    det, ev = detect_gather_scatter(feats, transactions=_gather_then_scatter_txs(), config=CFG)
    assert len(det) == 1 and len(ev) == 1
    assert det.iloc[0]["pattern_instance_id"] == ev[0]["pattern_instance_id"]
    assert det.iloc[0]["evidence_id"] == ev[0]["evidence_id"]


def test_split_filter() -> None:
    feats = pd.DataFrame(
        [
            _feat(account_key="T", sample_split="train", in_degree_7d=3, out_degree_7d=3),
            _feat(account_key="V", sample_split="val", in_degree_7d=3, out_degree_7d=3),
            _feat(account_key="X", sample_split="test", in_degree_7d=3, out_degree_7d=3),
        ]
    )
    # Same topology for each center
    start, _ = snapshot_window_bounds(date(2022, 9, 6))
    rows = []
    for center in ["T", "V", "X"]:
        for i, src in enumerate(["S1", "S2", "S3"]):
            rows.append(
                {
                    "transaction_id": f"{center}_IN{i}",
                    "occurred_at": start + pd.Timedelta(hours=1 + i),
                    "from_account_key": src,
                    "to_account_key": center,
                    "amount": 10.0,
                    "amount_received": 10.0,
                }
            )
        for i, dst in enumerate(["D1", "D2", "D3"]):
            rows.append(
                {
                    "transaction_id": f"{center}_OUT{i}",
                    "occurred_at": start + pd.Timedelta(hours=20 + i),
                    "from_account_key": center,
                    "to_account_key": dst,
                    "amount": 10.0,
                    "amount_received": 10.0,
                }
            )
    det, _ = detect_gather_scatter(
        feats, transactions=_tx_frame(rows), config=CFG, splits=["train", "val"]
    )
    assert set(det["account_key"]) == {"T", "V"}


def test_no_label_columns_and_schema() -> None:
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    det, _ = detect_gather_scatter(feats, transactions=_gather_then_scatter_txs(), config=CFG)
    assert_no_label_leakage(list(det.columns))
    assert list(det.columns) == list(DETECTION_COLUMNS)


def test_frozen_config_loads() -> None:
    cfg = load_gather_config()
    assert cfg["s_min"] == 5
    assert cfg["d_min"] == 5
    assert cfg["tolerance_hours"] == 0.0
    assert cfg["amount_ratio_lo"] == 0.2
    assert cfg["amount_ratio_hi"] == 5.0
    assert cfg["tuned_on"] == "val"
    assert cfg["temporal_rule"] == "median_inbound_le_median_outbound_plus_tolerance"


def test_determinism() -> None:
    feats = pd.DataFrame([_feat(in_degree_7d=3, out_degree_7d=3)])
    tx = _gather_then_scatter_txs()
    d1, e1 = detect_gather_scatter(feats, transactions=tx, config=CFG)
    d2, e2 = detect_gather_scatter(feats, transactions=tx, config=CFG)
    pd.testing.assert_frame_equal(d1, d2)
    assert e1 == e2
