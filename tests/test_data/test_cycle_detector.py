"""Unit tests for CYCLE detector — docs/graph_cycle_detector_spec.md."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.data.cycle_detector import (
    DETECTION_COLUMNS,
    canonicalize_accounts,
    detect_cycles,
    detect_cycles_for_snapshot,
    pattern_instance_id,
)
from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import assign_snapshot_split, snapshot_window_bounds

SNAPSHOT_D = date(2022, 9, 9)
CUTOFFS = {
    "train_end_ts": "2022-09-06 23:43:00+00:00",
    "val_end_ts": "2022-09-08 21:12:00+00:00",
}


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _tx(
    rows: list[tuple[str, str, str, str, float]],
) -> pd.DataFrame:
    """(transaction_id, occurred_at, from, to, amount)."""
    return pd.DataFrame(
        [
            {
                "transaction_id": tid,
                "occurred_at": _ts(o),
                "from_account_key": f,
                "to_account_key": t,
                "amount": a,
            }
            for tid, o, f, t, a in rows
        ]
    )


def test_canonicalize_accounts_lex_rotation() -> None:
    assert canonicalize_accounts(["C", "A", "B"]) == ["A", "B", "C"]
    assert canonicalize_accounts(["B", "C", "A"]) == ["A", "B", "C"]


def test_topology_without_time_valid_witness_no_emit() -> None:
    # A->B@18, B->C@12, C->A@10 — no non-decreasing rotation
    tx = _tx(
        [
            ("TX1", "2022-09-05T18:00:00", "A", "B", 1.0),
            ("TX2", "2022-09-05T12:00:00", "B", "C", 1.0),
            ("TX3", "2022-09-05T10:00:00", "C", "A", 1.0),
        ]
    )
    det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert det.empty
    assert ev == []


def test_multi_edge_witness_not_min_collapse() -> None:
    # Plan example: A→B TX1@01 and TX2@18; B→C TX3@12; C→A TX4@15
    # Valid witness: TX1, TX3, TX4
    tx = _tx(
        [
            ("TX1", "2022-09-05T01:00:00", "A", "B", 100.0),
            ("TX2", "2022-09-05T18:00:00", "A", "B", 200.0),
            ("TX3", "2022-09-05T12:00:00", "B", "C", 90.0),
            ("TX4", "2022-09-05T15:00:00", "C", "A", 80.0),
        ]
    )
    det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert len(ev) == 1
    assert ev[0]["transaction_ids"] == ["TX1", "TX3", "TX4"]
    times = [pd.Timestamp(h["occurred_at"]) for h in ev[0]["hops"]]
    assert times[0] <= times[1] <= times[2]
    assert set(det["account_key"]) == {"A", "B", "C"}
    assert det["pattern_instance_id"].nunique() == 1
    assert len(det) == 3


def test_equal_timestamps_allowed() -> None:
    tx = _tx(
        [
            ("T1", "2022-09-05T10:00:00", "A", "B", 1.0),
            ("T2", "2022-09-05T10:00:00", "B", "A", 1.0),
        ]
    )
    det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert len(ev) == 1
    assert ev[0]["cycle_length"] == 2
    assert len(det) == 2


def test_three_start_vertices_one_pattern_instance() -> None:
    tx = _tx(
        [
            ("T1", "2022-09-04T01:00:00", "A", "B", 1.0),
            ("T2", "2022-09-04T02:00:00", "B", "C", 1.0),
            ("T3", "2022-09-04T03:00:00", "C", "A", 1.0),
        ]
    )
    det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert len(ev) == 1
    assert det["pattern_instance_id"].nunique() == 1
    assert set(det["account_key"]) == {"A", "B", "C"}
    assert len(det) == 3
    # Motif accounts canonical
    assert ev[0]["accounts"] == canonicalize_accounts(["A", "B", "C"])


def test_length_6_ok_length_7_no() -> None:
    # Length 6 cycle
    nodes = [f"N{i}" for i in range(6)]
    rows = []
    for i in range(6):
        rows.append(
            (
                f"L6_{i}",
                f"2022-09-04T{i+1:02d}:00:00",
                nodes[i],
                nodes[(i + 1) % 6],
                1.0,
            )
        )
    det6, ev6 = detect_cycles_for_snapshot(_tx(rows), SNAPSHOT_D, CUTOFFS)
    assert any(e["cycle_length"] == 6 for e in ev6)
    assert not det6.empty

    # Length 7 — baseline max 6
    nodes7 = [f"M{i}" for i in range(7)]
    rows7 = []
    for i in range(7):
        rows7.append(
            (
                f"L7_{i}",
                f"2022-09-04T{i+1:02d}:00:00",
                nodes7[i],
                nodes7[(i + 1) % 7],
                1.0,
            )
        )
    det7, ev7 = detect_cycles_for_snapshot(_tx(rows7), SNAPSHOT_D, CUTOFFS)
    assert all(e["cycle_length"] != 7 for e in ev7)
    assert not any(c == 7 for c in det7["cycle_length"].tolist()) if len(det7) else True


def test_window_bounds_end_excluded() -> None:
    start_ts, end_ts = snapshot_window_bounds(SNAPSHOT_D)
    tx = _tx(
        [
            ("IN", start_ts.isoformat(), "A", "B", 1.0),
            ("MID", "2022-09-05T12:00:00", "B", "A", 1.0),
            ("OUT", end_ts.isoformat(), "A", "B", 99.0),  # excluded
            ("OUT2", (end_ts + pd.Timedelta(hours=1)).isoformat(), "B", "A", 99.0),
        ]
    )
    # Without OUT/OUT2 still have A<->B in window via IN and MID
    _det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert len(ev) == 1
    assert "OUT" not in ev[0]["transaction_ids"]


def test_sample_split_matches_helper() -> None:
    tx = _tx(
        [
            ("T1", "2022-09-05T01:00:00", "A", "B", 1.0),
            ("T2", "2022-09-05T02:00:00", "B", "A", 1.0),
        ]
    )
    det, _ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    _, end_ts = snapshot_window_bounds(SNAPSHOT_D)
    assert (det["sample_split"] == assign_snapshot_split(end_ts, CUTOFFS)).all()


def test_determinism() -> None:
    tx = _tx(
        [
            ("T1", "2022-09-05T01:00:00", "A", "B", 1.0),
            ("T2", "2022-09-05T02:00:00", "B", "C", 1.0),
            ("T3", "2022-09-05T03:00:00", "C", "A", 1.0),
        ]
    )
    d1, e1 = detect_cycles(tx, CUTOFFS, snapshot_dates=[SNAPSHOT_D])
    d2, e2 = detect_cycles(tx, CUTOFFS, snapshot_dates=[SNAPSHOT_D])
    pd.testing.assert_frame_equal(d1, d2)
    assert e1 == e2


def test_canonical_vs_witness_order_may_diverge() -> None:
    # Lex-canonical starts at A; choose times so witness starts at B
    # Path A->B->C->A with times that only work starting mid-cycle:
    # Use B@01 -> C@02 -> A@03 -> B needs A->B after A...
    # Simpler: accounts C, A, B lex starts at A,B,C
    # Witness time-valid only as B@01->C@02->A@03
    tx = _tx(
        [
            ("TB", "2022-09-05T01:00:00", "B", "C", 1.0),
            ("TC", "2022-09-05T02:00:00", "C", "A", 1.0),
            ("TA", "2022-09-05T03:00:00", "A", "B", 1.0),
        ]
    )
    _det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert len(ev) == 1
    assert ev[0]["accounts"] == ["A", "B", "C"]  # canonical
    # Witness hops non-decreasing; first hop may not start at A
    hops = ev[0]["hops"]
    times = [pd.Timestamp(h["occurred_at"]) for h in hops]
    assert times[0] <= times[1] <= times[2]
    assert hops[0]["from_account_key"] == "B"
    assert ev[0]["transaction_ids"] == ["TB", "TC", "TA"]
    # Set equality
    assert set(ev[0]["accounts"]) == {h["from_account_key"] for h in hops}


def test_hops_traceable_and_transaction_ids_mirror() -> None:
    tx = _tx(
        [
            ("TX1", "2022-09-05T01:00:00", "A", "B", 10.0),
            ("TX2", "2022-09-05T02:00:00", "B", "A", 20.0),
        ]
    )
    _det, ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    hops = ev[0]["hops"]
    assert ev[0]["transaction_ids"] == [h["transaction_id"] for h in hops]
    by_id = {r.transaction_id: r for r in tx.itertuples()}
    for h in hops:
        raw = by_id[h["transaction_id"]]
        assert raw.from_account_key == h["from_account_key"]
        assert raw.to_account_key == h["to_account_key"]


def test_no_label_columns() -> None:
    tx = _tx(
        [
            ("T1", "2022-09-05T01:00:00", "A", "B", 1.0),
            ("T2", "2022-09-05T02:00:00", "B", "A", 1.0),
        ]
    )
    det, _ev = detect_cycles_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert_no_label_leakage(list(det.columns))
    assert list(det.columns) == list(DETECTION_COLUMNS)


def test_pi_ignores_unused_parallel_tx() -> None:
    base = _tx(
        [
            ("TX1", "2022-09-05T01:00:00", "A", "B", 1.0),
            ("TX3", "2022-09-05T12:00:00", "B", "C", 1.0),
            ("TX4", "2022-09-05T15:00:00", "C", "A", 1.0),
        ]
    )
    extra = pd.concat(
        [
            base,
            _tx([("TX2", "2022-09-05T18:00:00", "A", "B", 9.0)]),
        ],
        ignore_index=True,
    )
    _d1, e1 = detect_cycles_for_snapshot(base, SNAPSHOT_D, CUTOFFS)
    _d2, e2 = detect_cycles_for_snapshot(extra, SNAPSHOT_D, CUTOFFS)
    assert e1[0]["pattern_instance_id"] == e2[0]["pattern_instance_id"]
    # Same chosen witness → same evidence_id
    assert e1[0]["evidence_id"] == e2[0]["evidence_id"]
    assert e1[0]["transaction_ids"] == e2[0]["transaction_ids"] == ["TX1", "TX3", "TX4"]


def test_pattern_instance_stable_formula() -> None:
    _, end_ts = snapshot_window_bounds(SNAPSHOT_D)
    a = pattern_instance_id(as_of_ts=end_ts, accounts=["A", "B", "C"])
    b = pattern_instance_id(as_of_ts=end_ts, accounts=["A", "B", "C"])
    assert a == b
    assert a.startswith("PI_CYCLE_")
