"""Graph feature computation — docs/graph_feature_spec.md (features only).

Primary engine: DuckDB SQL aggregations + first_seen counterparty tables.
Pandas path kept only as a small-data reference for semantic parity tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import (
    FEATURE_SCHEMA_VERSION,
    WINDOW_7D,
    assign_snapshot_split,
    candidate_snapshot_dates,
    load_split_cutoffs,
    snapshot_window_bounds,
)

REQUIRED_TX_COLUMNS = (
    "occurred_at",
    "from_account_key",
    "to_account_key",
    "amount",
    "amount_received",
)

OUTPUT_COLUMNS = (
    "account_key",
    "as_of_ts",
    "snapshot_date",
    "window",
    "sample_split",
    "feature_schema_version",
    "in_degree_7d",
    "out_degree_7d",
    "unique_neighbors_7d",
    "in_out_degree_ratio_7d",
    "new_in_counterparty_ratio_7d",
    "new_out_counterparty_ratio_7d",
    "inflow_concentration_7d",
    "outflow_dispersion_7d",
    "history_available",
    "history_days_observed",
)


def _ensure_tx_frame(transactions: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_TX_COLUMNS if c not in transactions.columns]
    if missing:
        raise ValueError(f"transactions missing columns: {missing}")
    df = transactions.loc[:, list(REQUIRED_TX_COLUMNS)].copy()
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["from_account_key"] = df["from_account_key"].astype(str)
    df["to_account_key"] = df["to_account_key"].astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="raise")
    df["amount_received"] = pd.to_numeric(df["amount_received"], errors="raise")
    return df


def _hhi_from_weights(weights: pd.Series) -> float:
    total = float(weights.sum())
    if total == 0.0:
        return 0.0
    shares = weights.astype(float) / total
    return float((shares**2).sum())


def in_out_degree_ratio(in_deg: int, out_deg: int) -> float:
    """Spec §7.4: (in - out) / (in + out); both zero → 0."""
    if in_deg == 0 and out_deg == 0:
        return 0.0
    return (in_deg - out_deg) / (in_deg + out_deg)


def _snapshots_frame(
    snapshot_dates: list[date], split_cutoffs: Mapping[str, Any]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for d in snapshot_dates:
        start_ts, end_ts = snapshot_window_bounds(d)
        rows.append(
            {
                "snapshot_date": d,
                "start_ts": start_ts.to_pydatetime(),
                "end_ts": end_ts.to_pydatetime(),
                "as_of_ts": end_ts.to_pydatetime(),
                "sample_split": assign_snapshot_split(end_ts, split_cutoffs),
                "window": WINDOW_7D,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
            }
        )
    return pd.DataFrame(rows)


def _normalize_feature_frame(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    out = out.copy()
    out["as_of_ts"] = pd.to_datetime(out["as_of_ts"], utc=True)
    if "snapshot_date" in out.columns:
        out["snapshot_date"] = pd.to_datetime(out["snapshot_date"]).dt.date
    for col in (
        "in_degree_7d",
        "out_degree_7d",
        "unique_neighbors_7d",
        "history_available",
        "history_days_observed",
    ):
        out[col] = out[col].astype(int)
    for col in (
        "in_out_degree_ratio_7d",
        "new_in_counterparty_ratio_7d",
        "new_out_counterparty_ratio_7d",
        "inflow_concentration_7d",
        "outflow_dispersion_7d",
    ):
        out[col] = out[col].astype(float)
    out = out.loc[:, list(OUTPUT_COLUMNS)]
    return out.sort_values(["as_of_ts", "account_key"], kind="mergesort").reset_index(drop=True)


_FEATURE_SQL = """
WITH in_edges AS (
  SELECT
    s.snapshot_date,
    s.start_ts,
    t.to_account_key AS account_key,
    t.from_account_key AS cp,
    SUM(t.amount_received) AS inflow
  FROM snapshots s
  JOIN tx t
    ON t.occurred_at >= s.start_ts AND t.occurred_at < s.end_ts
  GROUP BY 1, 2, 3, 4
),
out_edges AS (
  SELECT
    s.snapshot_date,
    s.start_ts,
    t.from_account_key AS account_key,
    t.to_account_key AS cp,
    SUM(t.amount) AS outflow
  FROM snapshots s
  JOIN tx t
    ON t.occurred_at >= s.start_ts AND t.occurred_at < s.end_ts
  GROUP BY 1, 2, 3, 4
),
in_tot AS (
  SELECT snapshot_date, account_key, SUM(inflow) AS total
  FROM in_edges
  GROUP BY 1, 2
),
out_tot AS (
  SELECT snapshot_date, account_key, SUM(outflow) AS total
  FROM out_edges
  GROUP BY 1, 2
),
in_stats AS (
  SELECT
    e.snapshot_date,
    e.account_key,
    COUNT(*)::BIGINT AS in_degree_7d,
    SUM(CASE WHEN f.first_seen IS NULL OR f.first_seen >= e.start_ts THEN 1 ELSE 0 END)::BIGINT
      AS n_new_in,
    CASE
      WHEN MAX(t.total) = 0 THEN 0.0
      ELSE SUM(POWER(e.inflow / t.total, 2))
    END AS inflow_concentration_7d
  FROM in_edges e
  JOIN in_tot t
    ON t.snapshot_date = e.snapshot_date AND t.account_key = e.account_key
  LEFT JOIN first_seen_in f
    ON f.account_key = e.account_key AND f.cp = e.cp
  GROUP BY 1, 2
),
out_stats AS (
  SELECT
    e.snapshot_date,
    e.account_key,
    COUNT(*)::BIGINT AS out_degree_7d,
    SUM(CASE WHEN f.first_seen IS NULL OR f.first_seen >= e.start_ts THEN 1 ELSE 0 END)::BIGINT
      AS n_new_out,
    CASE
      WHEN MAX(t.total) = 0 THEN 0.0
      ELSE 1.0 - SUM(POWER(e.outflow / t.total, 2))
    END AS outflow_dispersion_7d
  FROM out_edges e
  JOIN out_tot t
    ON t.snapshot_date = e.snapshot_date AND t.account_key = e.account_key
  LEFT JOIN first_seen_out f
    ON f.account_key = e.account_key AND f.cp = e.cp
  GROUP BY 1, 2
),
neighbors AS (
  SELECT snapshot_date, account_key, cp FROM in_edges
  UNION
  SELECT snapshot_date, account_key, cp FROM out_edges
),
neighbor_stats AS (
  SELECT snapshot_date, account_key, COUNT(*)::BIGINT AS unique_neighbors_7d
  FROM neighbors
  GROUP BY 1, 2
),
active AS (
  SELECT snapshot_date, account_key FROM neighbor_stats
),
hist_meta AS (
  SELECT
    s.snapshot_date,
    a.account_key,
    1 AS history_available,
    COUNT(DISTINCT CAST(ae.occurred_at AT TIME ZONE 'UTC' AS DATE))::BIGINT
      AS history_days_observed
  FROM snapshots s
  JOIN active a ON a.snapshot_date = s.snapshot_date
  JOIN account_event ae
    ON ae.account_key = a.account_key AND ae.occurred_at < s.start_ts
  GROUP BY 1, 2
)
SELECT
  a.account_key,
  s.as_of_ts,
  s.snapshot_date,
  s.win AS window,
  s.sample_split,
  s.feature_schema_version,
  COALESCE(i.in_degree_7d, 0)::BIGINT AS in_degree_7d,
  COALESCE(o.out_degree_7d, 0)::BIGINT AS out_degree_7d,
  n.unique_neighbors_7d,
  CASE
    WHEN COALESCE(i.in_degree_7d, 0) = 0 AND COALESCE(o.out_degree_7d, 0) = 0 THEN 0.0
    ELSE (COALESCE(i.in_degree_7d, 0) - COALESCE(o.out_degree_7d, 0))::DOUBLE
         / (COALESCE(i.in_degree_7d, 0) + COALESCE(o.out_degree_7d, 0))
  END AS in_out_degree_ratio_7d,
  CASE
    WHEN COALESCE(i.in_degree_7d, 0) = 0 THEN 0.0
    ELSE i.n_new_in::DOUBLE / i.in_degree_7d
  END AS new_in_counterparty_ratio_7d,
  CASE
    WHEN COALESCE(o.out_degree_7d, 0) = 0 THEN 0.0
    ELSE o.n_new_out::DOUBLE / o.out_degree_7d
  END AS new_out_counterparty_ratio_7d,
  COALESCE(i.inflow_concentration_7d, 0.0) AS inflow_concentration_7d,
  COALESCE(o.outflow_dispersion_7d, 0.0) AS outflow_dispersion_7d,
  COALESCE(h.history_available, 0)::BIGINT AS history_available,
  COALESCE(h.history_days_observed, 0)::BIGINT AS history_days_observed
FROM active a
JOIN snapshots s ON s.snapshot_date = a.snapshot_date
JOIN neighbor_stats n
  ON n.snapshot_date = a.snapshot_date AND n.account_key = a.account_key
LEFT JOIN in_stats i
  ON i.snapshot_date = a.snapshot_date AND i.account_key = a.account_key
LEFT JOIN out_stats o
  ON o.snapshot_date = a.snapshot_date AND o.account_key = a.account_key
LEFT JOIN hist_meta h
  ON h.snapshot_date = a.snapshot_date AND h.account_key = a.account_key
ORDER BY s.as_of_ts, a.account_key
"""


def _prepare_tx_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Build reusable first_seen + account_event tables from relation `tx`."""
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE first_seen_in AS
        SELECT
          to_account_key AS account_key,
          from_account_key AS cp,
          MIN(occurred_at) AS first_seen
        FROM tx
        GROUP BY 1, 2
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE first_seen_out AS
        SELECT
          from_account_key AS account_key,
          to_account_key AS cp,
          MIN(occurred_at) AS first_seen
        FROM tx
        GROUP BY 1, 2
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE account_event AS
        SELECT from_account_key AS account_key, occurred_at FROM tx
        UNION ALL
        SELECT to_account_key AS account_key, occurred_at FROM tx
        """
    )


def _candidate_dates_from_con(con: duckdb.DuckDBPyConnection) -> list[date]:
    row = con.execute(
        """
        SELECT MIN(occurred_at) AS t_min, MAX(occurred_at) AS t_max
        FROM tx
        """
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return []
    t_min = pd.Timestamp(row[0])
    t_max = pd.Timestamp(row[1])
    if t_min.tzinfo is None:
        t_min = t_min.tz_localize("UTC")
    else:
        t_min = t_min.tz_convert("UTC")
    if t_max.tzinfo is None:
        t_max = t_max.tz_localize("UTC")
    else:
        t_max = t_max.tz_convert("UTC")
    # Reuse shared helper via a tiny Series
    return candidate_snapshot_dates(pd.Series([t_min, t_max]))


def _register_snapshots(
    con: duckdb.DuckDBPyConnection,
    split_cutoffs: Mapping[str, Any],
    snapshot_dates: list[date] | None,
) -> list[date]:
    dates = snapshot_dates if snapshot_dates is not None else _candidate_dates_from_con(con)
    if not dates:
        return []
    snaps = _snapshots_frame(dates, split_cutoffs)
    con.register("snapshots_df", snaps)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE snapshots AS
        SELECT
          snapshot_date::DATE AS snapshot_date,
          start_ts::TIMESTAMPTZ AS start_ts,
          end_ts::TIMESTAMPTZ AS end_ts,
          as_of_ts::TIMESTAMPTZ AS as_of_ts,
          sample_split::VARCHAR AS sample_split,
          "window"::VARCHAR AS win,
          feature_schema_version::VARCHAR AS feature_schema_version
        FROM snapshots_df
        """
    )
    return dates


def _compute_from_prepared_con(
    con: duckdb.DuckDBPyConnection,
    split_cutoffs: Mapping[str, Any],
    snapshot_dates: list[date] | None,
) -> pd.DataFrame:
    dates = _register_snapshots(con, split_cutoffs, snapshot_dates)
    if not dates:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    _prepare_tx_tables(con)
    out = con.execute(_FEATURE_SQL).df()
    out = _normalize_feature_frame(out)
    assert_no_label_leakage(list(out.columns))
    return out


def _export_from_prepared_con(
    con: duckdb.DuckDBPyConnection,
    split_cutoffs: Mapping[str, Any],
    snapshot_dates: list[date] | None,
    out_path: Path,
) -> dict[str, Any]:
    """Compute features in DuckDB and COPY directly to parquet (no full pandas)."""
    assert_no_label_leakage(list(OUTPUT_COLUMNS))
    dates = _register_snapshots(con, split_cutoffs, snapshot_dates)
    if not dates:
        # Empty schema parquet for determinism
        empty = pd.DataFrame(columns=list(OUTPUT_COLUMNS))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        empty.to_parquet(out_path, index=False)
        return {"n_rows": 0, "n_snapshots": 0, "out_path": str(out_path)}

    _prepare_tx_tables(con)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write via DuckDB COPY — streams result without Python materialization
    con.execute(
        f"""
        COPY ({_FEATURE_SQL})
        TO '{out_path.resolve().as_posix()}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    n_rows = int(
        con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{out_path.resolve().as_posix()}')"
        ).fetchone()[0]
    )
    return {
        "n_rows": n_rows,
        "n_snapshots": len(dates),
        "snapshot_dates": dates,
        "out_path": str(out_path),
    }


def compute_graph_features_duckdb(
    transactions: pd.DataFrame,
    split_cutoffs: Mapping[str, Any],
    *,
    snapshot_dates: list[date] | None = None,
) -> pd.DataFrame:
    """DuckDB engine over an in-memory transaction frame (tests / small data)."""
    tx = _ensure_tx_frame(transactions)
    con = duckdb.connect()
    try:
        con.register("tx_raw", tx)
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE tx AS
            SELECT
              occurred_at::TIMESTAMPTZ AS occurred_at,
              from_account_key::VARCHAR AS from_account_key,
              to_account_key::VARCHAR AS to_account_key,
              amount::DOUBLE AS amount,
              amount_received::DOUBLE AS amount_received
            FROM tx_raw
            """
        )
        return _compute_from_prepared_con(con, split_cutoffs, snapshot_dates)
    finally:
        con.close()


def _open_aml_tx_relation(
    con: duckdb.DuckDBPyConnection,
    db_path: str | Path,
    *,
    range_start: datetime | pd.Timestamp | None = None,
    range_end_exclusive: datetime | pd.Timestamp | None = None,
) -> int:
    """ATTACH aml DB and expose filtered `tx` as a VIEW (no full copy)."""
    db_path = Path(db_path).resolve()
    con.execute(f"ATTACH '{db_path.as_posix()}' AS aml (READ_ONLY)")
    if range_start is not None or range_end_exclusive is not None:
        start = range_start if range_start is not None else datetime(1970, 1, 1, tzinfo=timezone.utc)
        end = (
            range_end_exclusive
            if range_end_exclusive is not None
            else datetime(2100, 1, 1, tzinfo=timezone.utc)
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP VIEW tx AS
            SELECT
              occurred_at,
              from_account_key,
              to_account_key,
              amount,
              amount_received
            FROM aml.transaction
            WHERE occurred_at >= ? AND occurred_at < ?
            """,
            [pd.Timestamp(start).to_pydatetime(), pd.Timestamp(end).to_pydatetime()],
        )
    else:
        con.execute(
            """
            CREATE OR REPLACE TEMP VIEW tx AS
            SELECT
              occurred_at,
              from_account_key,
              to_account_key,
              amount,
              amount_received
            FROM aml.transaction
            """
        )
    return int(con.execute("SELECT COUNT(*) FROM tx").fetchone()[0])


def compute_graph_features_from_duckdb(
    db_path: str | Path,
    split_cutoffs: Mapping[str, Any],
    *,
    snapshot_dates: list[date] | None = None,
    range_start: datetime | pd.Timestamp | None = None,
    range_end_exclusive: datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Aggregate inside DuckDB without pulling all transactions into pandas.

    Optional half-open filter on occurred_at for integration benches.
    """
    con = duckdb.connect()
    try:
        n = _open_aml_tx_relation(
            con,
            db_path,
            range_start=range_start,
            range_end_exclusive=range_end_exclusive,
        )
        if n == 0:
            return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
        return _compute_from_prepared_con(con, split_cutoffs, snapshot_dates)
    finally:
        con.close()


def export_graph_features_from_duckdb(
    db_path: str | Path,
    split_cutoffs: Mapping[str, Any],
    out_path: str | Path,
    *,
    snapshot_dates: list[date] | None = None,
    range_start: datetime | pd.Timestamp | None = None,
    range_end_exclusive: datetime | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Full/bench export: DuckDB aggregates → COPY parquet (no full pandas)."""
    con = duckdb.connect()
    try:
        # Prefer spilling to disk over OOM on large intermediates
        con.execute("SET memory_limit='12GB'")
        con.execute("SET temp_directory='/tmp/duckdb_graph_features_tmp'")
        Path("/tmp/duckdb_graph_features_tmp").mkdir(parents=True, exist_ok=True)
        n_tx = _open_aml_tx_relation(
            con,
            db_path,
            range_start=range_start,
            range_end_exclusive=range_end_exclusive,
        )
        if n_tx == 0:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=list(OUTPUT_COLUMNS)).to_parquet(out_path, index=False)
            return {"n_tx": 0, "n_rows": 0, "n_snapshots": 0, "out_path": str(out_path)}
        meta = _export_from_prepared_con(con, split_cutoffs, snapshot_dates, Path(out_path))
        meta["n_tx"] = n_tx
        return meta
    finally:
        con.close()


def compute_graph_features(
    transactions: pd.DataFrame,
    split_cutoffs: Mapping[str, Any],
    *,
    snapshot_dates: list[date] | None = None,
) -> pd.DataFrame:
    """Public API: DuckDB-backed feature computation (same formulas as spec)."""
    return compute_graph_features_duckdb(
        transactions, split_cutoffs, snapshot_dates=snapshot_dates
    )


def compute_features_for_snapshot(
    transactions: pd.DataFrame,
    snapshot_date: date,
    split_cutoffs: Mapping[str, Any],
) -> pd.DataFrame:
    """Compute graph feature rows for one snapshot date D (DuckDB engine)."""
    return compute_graph_features(
        transactions, split_cutoffs, snapshot_dates=[snapshot_date]
    )


# ---------------------------------------------------------------------------
# Pandas reference (semantic parity only — not used by production pipeline)
# ---------------------------------------------------------------------------


def compute_features_for_snapshot_pandas(
    transactions: pd.DataFrame,
    snapshot_date: date,
    split_cutoffs: Mapping[str, Any],
) -> pd.DataFrame:
    """Reference implementation matching spec; for parity tests only."""
    tx = _ensure_tx_frame(transactions)
    start_ts, end_ts = snapshot_window_bounds(snapshot_date)
    as_of_ts = end_ts
    sample_split = assign_snapshot_split(as_of_ts, split_cutoffs)

    w = tx.loc[(tx["occurred_at"] >= start_ts) & (tx["occurred_at"] < end_ts)]
    if w.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    active = pd.unique(
        pd.concat([w["from_account_key"], w["to_account_key"]], ignore_index=True)
    )

    in_sets: dict[str, set[str]] = (
        w.groupby("to_account_key", sort=False)["from_account_key"].agg(lambda s: set(s)).to_dict()
    )
    out_sets: dict[str, set[str]] = (
        w.groupby("from_account_key", sort=False)["to_account_key"].agg(lambda s: set(s)).to_dict()
    )

    hist = tx.loc[tx["occurred_at"] < start_ts]
    hist_in: dict[str, set[str]] = (
        hist.groupby("to_account_key", sort=False)["from_account_key"].agg(lambda s: set(s)).to_dict()
        if not hist.empty
        else {}
    )
    hist_out: dict[str, set[str]] = (
        hist.groupby("from_account_key", sort=False)["to_account_key"].agg(lambda s: set(s)).to_dict()
        if not hist.empty
        else {}
    )

    hist_dates: dict[str, set[date]] = {}
    if not hist.empty:
        hist = hist.copy()
        hist["_day"] = hist["occurred_at"].dt.floor("D").dt.date
        for col in ("from_account_key", "to_account_key"):
            for key, days in hist.groupby(col, sort=False)["_day"].agg(lambda s: set(s)).items():
                hist_dates.setdefault(str(key), set()).update(days)

    inflow_by_pair = w.groupby(["to_account_key", "from_account_key"], sort=False)[
        "amount_received"
    ].sum()
    outflow_by_pair = w.groupby(["from_account_key", "to_account_key"], sort=False)["amount"].sum()

    rows: list[dict[str, Any]] = []
    for account in active:
        a = str(account)
        in_set = in_sets.get(a, set())
        out_set = out_sets.get(a, set())
        in_deg = len(in_set)
        out_deg = len(out_set)
        neighbors = len(in_set | out_set)
        ratio = in_out_degree_ratio(in_deg, out_deg)

        hist_in_set = hist_in.get(a, set())
        hist_out_set = hist_out.get(a, set())
        new_in = 0.0 if in_deg == 0 else len(in_set - hist_in_set) / in_deg
        new_out = 0.0 if out_deg == 0 else len(out_set - hist_out_set) / out_deg

        if in_deg == 0:
            inflow_hhi = 0.0
        else:
            try:
                weights = inflow_by_pair.loc[a]
                inflow_hhi = (
                    _hhi_from_weights(weights) if isinstance(weights, pd.Series) else 1.0
                )
            except KeyError:
                inflow_hhi = 0.0

        if out_deg == 0:
            outflow_disp = 0.0
        else:
            try:
                weights = outflow_by_pair.loc[a]
                outflow_disp = (
                    1.0 - _hhi_from_weights(weights) if isinstance(weights, pd.Series) else 0.0
                )
            except KeyError:
                outflow_disp = 0.0

        days = hist_dates.get(a, set())
        rows.append(
            {
                "account_key": a,
                "as_of_ts": as_of_ts,
                "snapshot_date": snapshot_date,
                "window": WINDOW_7D,
                "sample_split": sample_split,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "in_degree_7d": int(in_deg),
                "out_degree_7d": int(out_deg),
                "unique_neighbors_7d": int(neighbors),
                "in_out_degree_ratio_7d": float(ratio),
                "new_in_counterparty_ratio_7d": float(new_in),
                "new_out_counterparty_ratio_7d": float(new_out),
                "inflow_concentration_7d": float(inflow_hhi),
                "outflow_dispersion_7d": float(outflow_disp),
                "history_available": int(1 if days else 0),
                "history_days_observed": int(len(days)),
            }
        )

    out = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
    if out.empty:
        return out
    return out.sort_values(["as_of_ts", "account_key"], kind="mergesort").reset_index(drop=True)


def compute_graph_features_pandas(
    transactions: pd.DataFrame,
    split_cutoffs: Mapping[str, Any],
    *,
    snapshot_dates: list[date] | None = None,
) -> pd.DataFrame:
    tx = _ensure_tx_frame(transactions)
    dates = snapshot_dates if snapshot_dates is not None else candidate_snapshot_dates(tx["occurred_at"])
    parts = [compute_features_for_snapshot_pandas(tx, d, split_cutoffs) for d in dates]
    if not parts:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    out = pd.concat(parts, ignore_index=True)
    if out.empty:
        return out
    out = out.sort_values(["as_of_ts", "account_key"], kind="mergesort").reset_index(drop=True)
    assert_no_label_leakage(list(out.columns))
    return out


def run_graph_feature_pipeline(
    *,
    db_path: str | Path | None = None,
    transactions: pd.DataFrame | None = None,
    cutoffs_path: str | Path | None = None,
    split_cutoffs: Mapping[str, Any] | None = None,
    out_path: str | Path | None = None,
    snapshot_dates: list[date] | None = None,
    range_start: datetime | pd.Timestamp | None = None,
    range_end_exclusive: datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Build graph_features_v1 and optionally write parquet.

    Prefer db_path (DuckDB-side aggregation). When both db_path and out_path are
    set, export via DuckDB COPY (no full pandas materialization) and return an
    empty frame; callers should read the parquet for row data.
    """
    if split_cutoffs is None:
        if cutoffs_path is None:
            raise ValueError("Provide cutoffs_path or split_cutoffs")
        split_cutoffs = load_split_cutoffs(cutoffs_path)

    if transactions is not None:
        features = compute_graph_features(
            transactions, split_cutoffs, snapshot_dates=snapshot_dates
        )
        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            features.to_parquet(out_path, index=False)
        return features

    if db_path is None:
        raise ValueError("Provide db_path or transactions")

    if out_path is not None:
        export_graph_features_from_duckdb(
            db_path,
            split_cutoffs,
            out_path,
            snapshot_dates=snapshot_dates,
            range_start=range_start,
            range_end_exclusive=range_end_exclusive,
        )
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    return compute_graph_features_from_duckdb(
        db_path,
        split_cutoffs,
        snapshot_dates=snapshot_dates,
        range_start=range_start,
        range_end_exclusive=range_end_exclusive,
    )
