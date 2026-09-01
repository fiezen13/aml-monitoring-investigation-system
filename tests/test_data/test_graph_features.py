"""Unit tests for graph features — docs/specification/data-model.md §5."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.data.graph_features import (
    OUTPUT_COLUMNS,
    compute_features_for_snapshot,
    compute_graph_features,
    in_out_degree_ratio,
    run_graph_feature_pipeline,
)
from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import (
    assign_snapshot_split,
    snapshot_window_bounds,
)

# Snapshot D=2022-09-09 → start=2022-09-03T00:00Z, end=as_of=2022-09-10T00:00Z
SNAPSHOT_D = date(2022, 9, 9)
CUTOFFS = {
    "train_end_ts": "2022-09-06 23:43:00+00:00",
    "val_end_ts": "2022-09-08 21:12:00+00:00",
}


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _tx(
    rows: list[tuple[str, str, str, float, float]],
) -> pd.DataFrame:
    """Build Task-1-shaped txs: (occurred_at, from, to, amount, amount_received)."""
    return pd.DataFrame(
        [
            {
                "occurred_at": _ts(o),
                "from_account_key": f,
                "to_account_key": t,
                "amount": a,
                "amount_received": ar,
            }
            for o, f, t, a, ar in rows
        ]
    )


def _row(features: pd.DataFrame, account: str) -> pd.Series:
    hit = features.loc[features["account_key"] == account]
    assert len(hit) == 1, f"expected 1 row for {account}, got {len(hit)}"
    return hit.iloc[0]


# --- §11: Window bounds ---


def test_window_bounds_start_included_end_excluded() -> None:
    start_ts, end_ts = snapshot_window_bounds(SNAPSHOT_D)
    assert start_ts == _ts("2022-09-03T00:00:00")
    assert end_ts == _ts("2022-09-10T00:00:00")

    tx = _tx(
        [
            ("2022-09-03T00:00:00", "S", "A", 10.0, 10.0),  # at start → include
            ("2022-09-10T00:00:00", "E", "A", 99.0, 99.0),  # at end → exclude
            ("2022-09-05T12:00:00", "B", "A", 5.0, 5.0),
        ]
    )
    feats = compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    a = _row(feats, "A")
    assert a["in_degree_7d"] == 2  # S and B only; E excluded
    assert "E" not in feats["account_key"].values or (
        # E only appears as sender at end_ts → no in-window activity
        len(feats.loc[feats["account_key"] == "E"]) == 0
    )


def test_future_leak_does_not_change_features() -> None:
    base = _tx(
        [
            ("2022-09-05T10:00:00", "X1", "A", 10.0, 10.0),
            ("2022-09-05T11:00:00", "A", "Y1", 20.0, 20.0),
        ]
    )
    leaked = pd.concat(
        [
            base,
            _tx(
                [
                    ("2022-09-10T00:00:00", "FUTURE", "A", 1000.0, 1000.0),
                    ("2022-09-11T00:00:00", "A", "FUTURE2", 2000.0, 2000.0),
                ]
            ),
        ],
        ignore_index=True,
    )
    f0 = compute_features_for_snapshot(base, SNAPSHOT_D, CUTOFFS)
    f1 = compute_features_for_snapshot(leaked, SNAPSHOT_D, CUTOFFS)
    cols = [c for c in OUTPUT_COLUMNS if c not in ("as_of_ts", "snapshot_date")]
    pd.testing.assert_frame_equal(
        f0.sort_values("account_key")[cols].reset_index(drop=True),
        f1.sort_values("account_key")[cols].reset_index(drop=True),
    )


def test_in_out_degree_unique_counts() -> None:
    # Fan-in to A from X1,X2,X1 again; fan-out from A to Y1,Y2
    tx = _tx(
        [
            ("2022-09-04T01:00:00", "X1", "A", 1.0, 1.0),
            ("2022-09-04T02:00:00", "X2", "A", 2.0, 2.0),
            ("2022-09-04T03:00:00", "X1", "A", 3.0, 3.0),
            ("2022-09-05T01:00:00", "A", "Y1", 4.0, 4.0),
            ("2022-09-05T02:00:00", "A", "Y2", 5.0, 5.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["in_degree_7d"] == 2
    assert a["out_degree_7d"] == 2


def test_unique_neighbors_bidirectional_once() -> None:
    # B is both inbound and outbound neighbor of A
    tx = _tx(
        [
            ("2022-09-04T01:00:00", "B", "A", 10.0, 10.0),
            ("2022-09-04T02:00:00", "A", "B", 20.0, 20.0),
            ("2022-09-04T03:00:00", "C", "A", 5.0, 5.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["in_degree_7d"] == 2  # B, C
    assert a["out_degree_7d"] == 1  # B
    assert a["unique_neighbors_7d"] == 2  # {B, C} once


def test_ratio_both_zero() -> None:
    assert in_out_degree_ratio(0, 0) == 0.0
    assert in_out_degree_ratio(1, 0) == pytest.approx(1.0)
    assert in_out_degree_ratio(0, 1) == pytest.approx(-1.0)
    assert in_out_degree_ratio(2, 2) == pytest.approx(0.0)


def test_new_in_ratio() -> None:
    tx = _tx(
        [
            # history before start_ts=2022-09-03
            ("2022-09-01T10:00:00", "OLD", "A", 1.0, 1.0),
            # window: OLD + NEW
            ("2022-09-05T10:00:00", "OLD", "A", 2.0, 2.0),
            ("2022-09-05T11:00:00", "NEW", "A", 3.0, 3.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["in_degree_7d"] == 2
    assert a["new_in_counterparty_ratio_7d"] == pytest.approx(0.5)
    assert a["history_available"] == 1


def test_new_out_ratio() -> None:
    tx = _tx(
        [
            ("2022-09-01T10:00:00", "A", "OLD", 1.0, 1.0),
            ("2022-09-05T10:00:00", "A", "OLD", 2.0, 2.0),
            ("2022-09-05T11:00:00", "A", "NEW", 3.0, 3.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["out_degree_7d"] == 2
    assert a["new_out_counterparty_ratio_7d"] == pytest.approx(0.5)
    assert a["history_available"] == 1


def test_hhi_single_source() -> None:
    tx = _tx(
        [
            ("2022-09-05T10:00:00", "S", "A", 10.0, 10.0),
            ("2022-09-05T11:00:00", "S", "A", 30.0, 30.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["inflow_concentration_7d"] == pytest.approx(1.0)


def test_dispersion_single_dest() -> None:
    tx = _tx(
        [
            ("2022-09-05T10:00:00", "A", "D", 10.0, 10.0),
            ("2022-09-05T11:00:00", "A", "D", 30.0, 30.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["outflow_dispersion_7d"] == pytest.approx(0.0)


def test_zero_flow_concentration_and_dispersion() -> None:
    inbound_only = _tx([("2022-09-05T10:00:00", "S", "A", 5.0, 5.0)])
    a = _row(compute_features_for_snapshot(inbound_only, SNAPSHOT_D, CUTOFFS), "A")
    assert a["out_degree_7d"] == 0
    assert a["outflow_dispersion_7d"] == pytest.approx(0.0)

    outbound_only = _tx([("2022-09-05T10:00:00", "A", "D", 5.0, 5.0)])
    a2 = _row(compute_features_for_snapshot(outbound_only, SNAPSHOT_D, CUTOFFS), "A")
    assert a2["in_degree_7d"] == 0
    assert a2["inflow_concentration_7d"] == pytest.approx(0.0)


def test_cold_start_no_history() -> None:
    tx = _tx(
        [
            ("2022-09-05T10:00:00", "X", "A", 10.0, 10.0),
            ("2022-09-05T11:00:00", "A", "Y", 20.0, 20.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["history_available"] == 0
    assert a["history_days_observed"] == 0
    assert a["new_in_counterparty_ratio_7d"] == pytest.approx(1.0)
    assert a["new_out_counterparty_ratio_7d"] == pytest.approx(1.0)


def test_with_history_excludes_known_counterparties() -> None:
    tx = _tx(
        [
            ("2022-09-01T08:00:00", "OLD_IN", "A", 1.0, 1.0),
            ("2022-09-02T08:00:00", "A", "OLD_OUT", 1.0, 1.0),
            ("2022-09-05T10:00:00", "OLD_IN", "A", 2.0, 2.0),
            ("2022-09-05T11:00:00", "NEW_IN", "A", 3.0, 3.0),
            ("2022-09-05T12:00:00", "A", "OLD_OUT", 4.0, 4.0),
            ("2022-09-05T13:00:00", "A", "NEW_OUT", 5.0, 5.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["history_available"] == 1
    assert a["history_days_observed"] == 2  # Sep 1 and Sep 2
    assert a["new_in_counterparty_ratio_7d"] == pytest.approx(0.5)
    assert a["new_out_counterparty_ratio_7d"] == pytest.approx(0.5)


def test_assign_snapshot_split_boundaries() -> None:
    assert assign_snapshot_split("2022-09-06 23:43:00+00:00", CUTOFFS) == "train"
    assert assign_snapshot_split("2022-09-07 00:00:00+00:00", CUTOFFS) == "val"
    assert assign_snapshot_split("2022-09-08 21:12:00+00:00", CUTOFFS) == "val"
    assert assign_snapshot_split("2022-09-08 21:12:01+00:00", CUTOFFS) == "test"
    # Snapshot as_of for D=2022-09-09 is 2022-09-10 → test
    _, end_ts = snapshot_window_bounds(SNAPSHOT_D)
    assert assign_snapshot_split(end_ts, CUTOFFS) == "test"


def test_sample_eligibility_no_row_without_in_window_tx() -> None:
    tx = _tx(
        [
            ("2022-09-01T10:00:00", "GHOST", "OTHER", 1.0, 1.0),  # history only
            ("2022-09-05T10:00:00", "X", "A", 1.0, 1.0),
        ]
    )
    feats = compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS)
    assert "GHOST" not in feats["account_key"].values
    assert "A" in feats["account_key"].values


def test_label_leak_absent_in_output() -> None:
    tx = _tx([("2022-09-05T10:00:00", "X", "A", 1.0, 1.0)])
    feats = compute_graph_features(tx, CUTOFFS, snapshot_dates=[SNAPSHOT_D])
    assert_no_label_leakage(list(feats.columns))
    assert list(feats.columns) == list(OUTPUT_COLUMNS)
    assert not any(c.startswith("label_") for c in feats.columns)


def test_determinism_identical_outputs(tmp_path: Path) -> None:
    tx = _tx(
        [
            ("2022-09-01T10:00:00", "OLD", "A", 1.0, 1.0),
            ("2022-09-05T10:00:00", "OLD", "A", 2.0, 2.0),
            ("2022-09-05T11:00:00", "B", "A", 3.0, 3.0),
            ("2022-09-05T12:00:00", "A", "C", 4.0, 4.0),
            ("2022-09-05T13:00:00", "A", "D", 6.0, 6.0),
        ]
    )
    out1 = tmp_path / "g1.parquet"
    out2 = tmp_path / "g2.parquet"
    f1 = run_graph_feature_pipeline(
        transactions=tx,
        split_cutoffs=CUTOFFS,
        out_path=out1,
        snapshot_dates=[SNAPSHOT_D],
    )
    f2 = run_graph_feature_pipeline(
        transactions=tx,
        split_cutoffs=CUTOFFS,
        out_path=out2,
        snapshot_dates=[SNAPSHOT_D],
    )
    pd.testing.assert_frame_equal(f1, f2)
    pd.testing.assert_frame_equal(pd.read_parquet(out1), pd.read_parquet(out2))


def test_hhi_two_equal_sources() -> None:
    tx = _tx(
        [
            ("2022-09-05T10:00:00", "S1", "A", 50.0, 50.0),
            ("2022-09-05T11:00:00", "S2", "A", 50.0, 50.0),
        ]
    )
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["inflow_concentration_7d"] == pytest.approx(0.5)


def test_sample_split_on_feature_row() -> None:
    tx = _tx([("2022-09-05T10:00:00", "X", "A", 1.0, 1.0)])
    a = _row(compute_features_for_snapshot(tx, SNAPSHOT_D, CUTOFFS), "A")
    assert a["sample_split"] == "test"
    assert a["window"] == "7d"
    assert a["feature_schema_version"] == "graph_features_v1"
    assert pd.Timestamp(a["as_of_ts"]) == _ts("2022-09-10T00:00:00")


def test_duckdb_matches_pandas_reference_semantics() -> None:
    """Optimized DuckDB engine must match pandas reference on a small fixture."""
    from src.data.graph_features import (
        compute_graph_features_duckdb,
        compute_graph_features_pandas,
    )

    tx = _tx(
        [
            ("2022-09-01T08:00:00", "OLD_IN", "A", 1.0, 1.0),
            ("2022-09-02T08:00:00", "A", "OLD_OUT", 1.0, 1.0),
            ("2022-09-04T01:00:00", "X1", "A", 10.0, 10.0),
            ("2022-09-04T02:00:00", "X2", "A", 30.0, 30.0),
            ("2022-09-04T03:00:00", "X1", "A", 10.0, 10.0),
            ("2022-09-05T01:00:00", "A", "Y1", 5.0, 5.0),
            ("2022-09-05T02:00:00", "A", "Y2", 5.0, 5.0),
            ("2022-09-05T03:00:00", "A", "OLD_OUT", 20.0, 20.0),
            ("2022-09-05T04:00:00", "B", "C", 7.0, 7.0),
            ("2022-09-05T05:00:00", "C", "B", 3.0, 3.0),
            ("2022-09-10T00:00:00", "FUTURE", "A", 999.0, 999.0),  # excluded from D=9
        ]
    )
    dates = [date(2022, 9, 5), date(2022, 9, 9)]
    duck = compute_graph_features_duckdb(tx, CUTOFFS, snapshot_dates=dates)
    ref = compute_graph_features_pandas(tx, CUTOFFS, snapshot_dates=dates)
    # Float tolerance for HHI shares
    pd.testing.assert_frame_equal(
        duck.reset_index(drop=True),
        ref.reset_index(drop=True),
        rtol=0,
        atol=1e-9,
        check_dtype=False,
    )
