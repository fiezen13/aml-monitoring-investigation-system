"""GATHER_SCATTER detector — median-based temporal baseline.

Contract: docs/specification/technical-design.md §2.1 (center = subject).
Frozen baseline: configs/graph/graph_gather_config_v1.json (tuned on val; no test/GT).

Rule:
  |S| >= s_min, |D| >= d_min
  median(occurred_at | inbound) <= median(occurred_at | outbound) + tolerance_hours
  amount_ratio = sum(amount out) / sum(amount_received in) in [r_lo, r_hi]
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import WINDOW_7D, parse_utc, snapshot_window_bounds

DETECTED_PATTERN = "GATHER_SCATTER"

DETECTION_COLUMNS = (
    "detection_id",
    "pattern_instance_id",
    "evidence_id",
    "account_key",
    "as_of_ts",
    "snapshot_date",
    "window",
    "sample_split",
    "detected_pattern",
    "detector_version",
    "cycle_length",
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs/graph/graph_gather_config_v1.json"


def _sha1_16(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_gather_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def pattern_instance_id_gather(
    *,
    account_key: str,
    as_of_ts: pd.Timestamp,
    detector_version: str,
    window: str = WINDOW_7D,
) -> str:
    as_of = parse_utc(as_of_ts).isoformat()
    key = "|".join([as_of, window, detector_version, DETECTED_PATTERN, account_key])
    return f"PI_{DETECTED_PATTERN}_{_sha1_16(key)}"


def evidence_id_gather(pi: str) -> str:
    return f"EV_{_sha1_16(pi)}"


def detection_id_gather(pi: str, account_key: str) -> str:
    return f"DET_{_sha1_16(pi + '|' + account_key)}"


def _passes_rules(
    *,
    n_in_cp: int,
    n_out_cp: int,
    sum_in: float,
    sum_out: float,
    med_in: float,
    med_out: float,
    cfg: Mapping[str, Any],
) -> bool:
    if n_in_cp < int(cfg["s_min"]) or n_out_cp < int(cfg["d_min"]):
        return False
    if sum_in <= 0:
        return False
    ratio = sum_out / sum_in
    if not (float(cfg["amount_ratio_lo"]) <= ratio <= float(cfg["amount_ratio_hi"])):
        return False
    tol_s = float(cfg["tolerance_hours"]) * 3600.0
    return med_in <= med_out + tol_s


def _as_date(value: Any) -> Any:
    if hasattr(value, "date") and callable(value.date) and not isinstance(value, type):
        try:
            return value.date()
        except Exception:
            pass
    return pd.Timestamp(value).date()


def _candidate_features(
    features: pd.DataFrame,
    cfg: Mapping[str, Any],
    splits: list[str] | None,
) -> pd.DataFrame:
    required = {
        "account_key",
        "as_of_ts",
        "snapshot_date",
        "window",
        "sample_split",
        "in_degree_7d",
        "out_degree_7d",
    }
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"features missing columns: {sorted(missing)}")

    df = features.copy()
    df["as_of_ts"] = pd.to_datetime(df["as_of_ts"], utc=True)
    if splits is not None:
        df = df.loc[df["sample_split"].isin(splits)]
    s_min, d_min = int(cfg["s_min"]), int(cfg["d_min"])
    return df.loc[(df["in_degree_7d"] >= s_min) & (df["out_degree_7d"] >= d_min)].reset_index(drop=True)


def evaluate_gather_on_transactions(
    candidates: pd.DataFrame,
    transactions: pd.DataFrame,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate GATHER rules for candidate feature rows against a TX frame (unit tests)."""
    cfg = dict(config)
    tx = transactions.copy()
    tx["occurred_at"] = pd.to_datetime(tx["occurred_at"], utc=True)
    hits: list[dict[str, Any]] = []

    for rec in candidates.to_dict(orient="records"):
        snap_d = _as_date(rec["snapshot_date"])
        start_ts, end_ts = snapshot_window_bounds(snap_d)
        account = str(rec["account_key"])
        w = tx.loc[
            (tx["occurred_at"] >= start_ts)
            & (tx["occurred_at"] < end_ts)
            & ((tx["to_account_key"] == account) | (tx["from_account_key"] == account))
        ]
        inn = w.loc[w["to_account_key"] == account]
        outt = w.loc[w["from_account_key"] == account]
        if inn.empty or outt.empty:
            continue
        n_in_cp = int(inn["from_account_key"].nunique())
        n_out_cp = int(outt["to_account_key"].nunique())
        sum_in = float(inn["amount_received"].sum())
        sum_out = float(outt["amount"].sum())
        med_in = float(inn["occurred_at"].astype("int64").median() / 1e9)
        med_out = float(outt["occurred_at"].astype("int64").median() / 1e9)
        if not _passes_rules(
            n_in_cp=n_in_cp,
            n_out_cp=n_out_cp,
            sum_in=sum_in,
            sum_out=sum_out,
            med_in=med_in,
            med_out=med_out,
            cfg=cfg,
        ):
            continue
        sources = sorted(inn["from_account_key"].astype(str).unique().tolist())
        destinations = sorted(outt["to_account_key"].astype(str).unique().tolist())
        gather_tids = sorted(inn["transaction_id"].astype(str).unique().tolist())
        scatter_tids = sorted(outt["transaction_id"].astype(str).unique().tolist())
        hits.append(
            {
                "account_key": account,
                "as_of_ts": parse_utc(rec["as_of_ts"]),
                "snapshot_date": snap_d,
                "window": str(rec.get("window") or WINDOW_7D),
                "sample_split": str(rec["sample_split"]),
                "n_in_cp": n_in_cp,
                "n_out_cp": n_out_cp,
                "sum_in": sum_in,
                "sum_out": sum_out,
                "med_in_epoch": med_in,
                "med_out_epoch": med_out,
                "amount_ratio": sum_out / sum_in,
                "sources": sources,
                "destinations": destinations,
                "gather_transaction_ids": gather_tids,
                "scatter_transaction_ids": scatter_tids,
            }
        )
    return hits


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and np.isnan(value):
        return []
    if isinstance(value, np.ndarray):
        return [str(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]


def evaluate_gather_duckdb(
    candidates: pd.DataFrame,
    *,
    duckdb_path: str | Path,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Batch-evaluate candidates against aml.duckdb (production path; matches freeze SQL)."""
    cfg = dict(config)
    if candidates.empty:
        return []

    db = Path(duckdb_path).resolve().as_posix()
    con = duckdb.connect()
    con.execute(f"ATTACH '{db}' AS aml (READ_ONLY)")
    con.register("cands_df", candidates)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE cands AS
        SELECT account_key,
               CAST(snapshot_date AS DATE) AS snapshot_date,
               as_of_ts,
               sample_split,
               "window",
               (as_of_ts - INTERVAL 7 DAY) AS start_ts,
               as_of_ts AS end_ts
        FROM cands_df
        """
    )
    rows = con.execute(
        """
        WITH inn AS (
          SELECT c.account_key, c.snapshot_date, c.sample_split, c.as_of_ts, c."window",
                 t.from_account_key AS cp,
                 epoch(t.occurred_at) AS t_epoch,
                 t.amount_received AS amt,
                 CAST(t.transaction_id AS VARCHAR) AS tid
          FROM cands c
          JOIN aml.transaction t
            ON t.to_account_key = c.account_key
           AND t.occurred_at >= c.start_ts
           AND t.occurred_at < c.end_ts
        ),
        outt AS (
          SELECT c.account_key, c.snapshot_date, c.sample_split, c.as_of_ts, c."window",
                 t.to_account_key AS cp,
                 epoch(t.occurred_at) AS t_epoch,
                 t.amount AS amt,
                 CAST(t.transaction_id AS VARCHAR) AS tid
          FROM cands c
          JOIN aml.transaction t
            ON t.from_account_key = c.account_key
           AND t.occurred_at >= c.start_ts
           AND t.occurred_at < c.end_ts
        ),
        in_agg AS (
          SELECT account_key, snapshot_date, sample_split, as_of_ts, "window",
                 COUNT(DISTINCT cp) AS n_in_cp,
                 SUM(amt) AS sum_in,
                 quantile_cont(t_epoch, 0.5) AS med_in,
                 list_sort(list_distinct(list(cp))) AS sources,
                 list_sort(list_distinct(list(tid))) AS gather_tids
          FROM inn
          GROUP BY 1,2,3,4,5
        ),
        out_agg AS (
          SELECT account_key, snapshot_date, sample_split, as_of_ts, "window",
                 COUNT(DISTINCT cp) AS n_out_cp,
                 SUM(amt) AS sum_out,
                 quantile_cont(t_epoch, 0.5) AS med_out,
                 list_sort(list_distinct(list(cp))) AS destinations,
                 list_sort(list_distinct(list(tid))) AS scatter_tids
          FROM outt
          GROUP BY 1,2,3,4,5
        )
        SELECT i.*,
               o.n_out_cp, o.sum_out, o.med_out, o.destinations, o.scatter_tids
        FROM in_agg i
        JOIN out_agg o
          USING (account_key, snapshot_date, sample_split, as_of_ts, "window")
        """
    ).fetchdf()
    con.close()

    hits: list[dict[str, Any]] = []
    for rec in rows.to_dict(orient="records"):
        n_in = int(rec["n_in_cp"])
        n_out = int(rec["n_out_cp"])
        sum_in = float(rec["sum_in"])
        sum_out = float(rec["sum_out"])
        med_in = float(rec["med_in"])
        med_out = float(rec["med_out"])
        if not _passes_rules(
            n_in_cp=n_in,
            n_out_cp=n_out,
            sum_in=sum_in,
            sum_out=sum_out,
            med_in=med_in,
            med_out=med_out,
            cfg=cfg,
        ):
            continue
        snap_d = _as_date(rec["snapshot_date"])
        sources = _as_str_list(rec["sources"])
        destinations = _as_str_list(rec["destinations"])
        gather_tids = _as_str_list(rec["gather_tids"])
        scatter_tids = _as_str_list(rec["scatter_tids"])
        hits.append(
            {
                "account_key": str(rec["account_key"]),
                "as_of_ts": parse_utc(rec["as_of_ts"]),
                "snapshot_date": snap_d,
                "window": str(rec["window"] or WINDOW_7D),
                "sample_split": str(rec["sample_split"]),
                "n_in_cp": n_in,
                "n_out_cp": n_out,
                "sum_in": sum_in,
                "sum_out": sum_out,
                "med_in_epoch": med_in,
                "med_out_epoch": med_out,
                "amount_ratio": sum_out / sum_in,
                "sources": sources,
                "destinations": destinations,
                "gather_transaction_ids": gather_tids,
                "scatter_transaction_ids": scatter_tids,
            }
        )
    return hits


def _emit_from_hits(
    hits: list[dict[str, Any]],
    cfg: Mapping[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    version = str(cfg["detector_version"])
    det_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for h in hits:
        account = h["account_key"]
        as_of = parse_utc(h["as_of_ts"])
        snap = h["snapshot_date"]
        snap_s = snap.isoformat() if hasattr(snap, "isoformat") else str(snap)
        window = h["window"]
        sample_split = h["sample_split"]
        pi = pattern_instance_id_gather(
            account_key=account,
            as_of_ts=as_of,
            detector_version=version,
            window=window,
        )
        ev = evidence_id_gather(pi)
        accounts = sorted(set([account] + h["sources"] + h["destinations"]))
        tids = sorted(set(h["gather_transaction_ids"] + h["scatter_transaction_ids"]))
        metrics = {
            "n_in_cp": h["n_in_cp"],
            "n_out_cp": h["n_out_cp"],
            "sum_in": h["sum_in"],
            "sum_out": h["sum_out"],
            "med_in_epoch": h["med_in_epoch"],
            "med_out_epoch": h["med_out_epoch"],
            "amount_ratio": h["amount_ratio"],
            "s_min": int(cfg["s_min"]),
            "d_min": int(cfg["d_min"]),
            "tolerance_hours": float(cfg["tolerance_hours"]),
            "amount_ratio_lo": float(cfg["amount_ratio_lo"]),
            "amount_ratio_hi": float(cfg["amount_ratio_hi"]),
            "temporal_rule": cfg.get("temporal_rule", "median_inbound_le_median_outbound_plus_tolerance"),
        }
        for k, v in list(metrics.items()):
            if isinstance(v, (np.floating, np.integer)):
                metrics[k] = v.item()

        det_rows.append(
            {
                "detection_id": detection_id_gather(pi, account),
                "pattern_instance_id": pi,
                "evidence_id": ev,
                "account_key": account,
                "as_of_ts": as_of,
                "snapshot_date": snap,
                "window": window,
                "sample_split": sample_split,
                "detected_pattern": DETECTED_PATTERN,
                "detector_version": version,
                "cycle_length": pd.NA,
            }
        )
        evidence.append(
            {
                "evidence_id": ev,
                "pattern_instance_id": pi,
                "as_of_ts": as_of.isoformat(),
                "snapshot_date": snap_s,
                "window": window,
                "sample_split": sample_split,
                "detected_pattern": DETECTED_PATTERN,
                "detector_version": version,
                "accounts": accounts,
                "transaction_ids": tids,
                "hops": [],
                "gather_transaction_ids": h["gather_transaction_ids"],
                "scatter_transaction_ids": h["scatter_transaction_ids"],
                "sources": h["sources"],
                "destinations": h["destinations"],
                "metrics": metrics,
                "cycle_length": None,
                "duration_hours": (h["med_out_epoch"] - h["med_in_epoch"]) / 3600.0,
            }
        )

    detections = pd.DataFrame(det_rows, columns=list(DETECTION_COLUMNS))
    if not detections.empty:
        detections = detections.sort_values(["as_of_ts", "account_key"], kind="mergesort").reset_index(drop=True)
    assert_no_label_leakage(list(detections.columns))
    return detections, evidence


def detect_gather_scatter(
    features: pd.DataFrame,
    *,
    transactions: pd.DataFrame | None = None,
    duckdb_path: str | Path | None = None,
    config: Mapping[str, Any] | None = None,
    splits: list[str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Emit GATHER_SCATTER detections + evidence.

    Provide either ``transactions`` (pandas, for tests) or ``duckdb_path`` (production).
    One hit → one pattern_instance_id, one evidence_id, one detection_id (center).
    """
    cfg = dict(config) if config is not None else load_gather_config()
    cands = _candidate_features(features, cfg, splits)
    if cands.empty:
        empty = pd.DataFrame(columns=list(DETECTION_COLUMNS))
        assert_no_label_leakage(list(empty.columns))
        return empty, []

    if transactions is not None:
        hits = evaluate_gather_on_transactions(cands, transactions, cfg)
    elif duckdb_path is not None:
        hits = evaluate_gather_duckdb(cands, duckdb_path=duckdb_path, config=cfg)
    else:
        raise ValueError("provide transactions= or duckdb_path=")

    return _emit_from_hits(hits, cfg)


def merge_gather_into_artifacts(
    gather_detections: pd.DataFrame,
    gather_evidence: list[dict[str, Any]],
    *,
    detection_path: str | Path,
    evidence_path: str | Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Replace any prior GATHER_SCATTER rows in existing FAN (+other) artifacts."""
    detection_path = Path(detection_path)
    evidence_path = Path(evidence_path)

    if detection_path.exists():
        existing = pd.read_parquet(detection_path)
        keep = existing.loc[existing["detected_pattern"] != DETECTED_PATTERN]
        combined = pd.concat([keep, gather_detections], ignore_index=True)
    else:
        combined = gather_detections.copy()

    if not combined.empty:
        combined = combined.sort_values(["as_of_ts", "detected_pattern", "account_key"], kind="mergesort").reset_index(
            drop=True
        )

    existing_ev: list[dict[str, Any]] = []
    if evidence_path.exists():
        with evidence_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("detected_pattern") != DETECTED_PATTERN:
                    existing_ev.append(rec)
    combined_ev = existing_ev + gather_evidence

    detection_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(detection_path, index=False)
    with evidence_path.open("w", encoding="utf-8") as f:
        for rec in combined_ev:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return combined, combined_ev


def run_gather_scatter_detector(
    *,
    features_path: str | Path,
    duckdb_path: str | Path,
    config_path: str | Path | None = None,
    detection_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
    splits: list[str] | None = None,
    merge_existing: bool = True,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    cfg = load_gather_config(config_path)
    features = pd.read_parquet(features_path)
    detections, evidence = detect_gather_scatter(
        features,
        duckdb_path=duckdb_path,
        config=cfg,
        splits=splits,
    )
    if detection_path is not None and evidence_path is not None:
        if merge_existing:
            return merge_gather_into_artifacts(
                detections,
                evidence,
                detection_path=detection_path,
                evidence_path=evidence_path,
            )
        Path(detection_path).parent.mkdir(parents=True, exist_ok=True)
        detections.to_parquet(detection_path, index=False)
        with Path(evidence_path).open("w", encoding="utf-8") as f:
            for rec in evidence:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return detections, evidence
