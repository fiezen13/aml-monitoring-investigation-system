"""FAN_IN / FAN_OUT detectors from graph_features_v1 — configurable thresholds.

Contract: docs/graph_branch_plan.md §4.2–4.3 / §5.1 (center = subject).
Frozen baseline configs are versioned under configs/graph/.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import WINDOW_7D, parse_utc

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

FAN_PATTERNS = ("FAN_IN", "FAN_OUT")

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs/graph/graph_fan_config_v3.json"
)


def compute_fan_auxiliary_duckdb(
    features: pd.DataFrame,
    *,
    duckdb_path: str | Path,
    min_degree: int = 2,
) -> pd.DataFrame:
    """Compute v3-min tx count and UTC-day counterparty burst for broad candidates."""
    required = {
        "account_key", "as_of_ts", "snapshot_date", "window", "sample_split",
        "in_degree_7d", "out_degree_7d", "inflow_concentration_7d",
        "outflow_dispersion_7d",
    }
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"features missing columns: {sorted(missing)}")
    base = features.copy()
    base["as_of_ts"] = pd.to_datetime(base["as_of_ts"], utc=True)
    con = duckdb.connect()
    try:
        con.register("feature_rows", base)
        con.execute(f"ATTACH '{Path(duckdb_path).resolve().as_posix()}' AS aml (READ_ONLY)")
        return con.execute(
            """
            WITH candidates AS (
              SELECT account_key, as_of_ts, snapshot_date, "window", sample_split,
                     'FAN_IN' AS detected_pattern, in_degree_7d AS degree_7d,
                     inflow_concentration_7d AS shape_7d
              FROM feature_rows WHERE in_degree_7d >= $min_degree
              UNION ALL
              SELECT account_key, as_of_ts, snapshot_date, "window", sample_split,
                     'FAN_OUT', out_degree_7d, outflow_dispersion_7d
              FROM feature_rows WHERE out_degree_7d >= $min_degree
            ), edges AS (
              SELECT c.*, CAST(t.occurred_at AT TIME ZONE 'UTC' AS DATE) AS tx_day,
                     t.from_account_key AS counterparty
              FROM candidates c JOIN aml.transaction t
                ON c.detected_pattern='FAN_IN' AND t.to_account_key=c.account_key
               AND t.occurred_at >= c.as_of_ts-INTERVAL 7 DAY AND t.occurred_at<c.as_of_ts
              UNION ALL
              SELECT c.*, CAST(t.occurred_at AT TIME ZONE 'UTC' AS DATE), t.to_account_key
              FROM candidates c JOIN aml.transaction t
                ON c.detected_pattern='FAN_OUT' AND t.from_account_key=c.account_key
               AND t.occurred_at >= c.as_of_ts-INTERVAL 7 DAY AND t.occurred_at<c.as_of_ts
            ), daily AS (
              SELECT account_key,as_of_ts,snapshot_date,"window",sample_split,
                     detected_pattern,degree_7d,shape_7d,tx_day,
                     COUNT(*) AS day_tx_count, COUNT(DISTINCT counterparty) AS day_cp_count
              FROM edges GROUP BY ALL
            )
            SELECT account_key,as_of_ts,snapshot_date,"window",sample_split,
                   detected_pattern,degree_7d,shape_7d,
                   SUM(day_tx_count)::BIGINT AS tx_count_7d,
                   MAX(day_cp_count)::BIGINT AS max_counterparties_1d,
                   MAX(day_cp_count)::DOUBLE/degree_7d AS counterparty_day_concentration
            FROM daily GROUP BY account_key,as_of_ts,snapshot_date,"window",sample_split,
                                detected_pattern,degree_7d,shape_7d
            ORDER BY as_of_ts,detected_pattern,account_key
            """,
            {"min_degree": min_degree},
        ).fetchdf()
    finally:
        con.close()


def select_fan_v3_min_hits(auxiliary: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    """Apply frozen, non-supervised v3-min rules to auxiliary measurements."""
    required = {"detected_pattern", "degree_7d", "shape_7d", "tx_count_7d", "counterparty_day_concentration"}
    missing = required - set(auxiliary.columns)
    if missing:
        raise ValueError(f"auxiliary missing columns: {sorted(missing)}")
    hits = []
    for pattern, key in (("FAN_IN", "fan_in"), ("FAN_OUT", "fan_out")):
        rule = config[key]
        z = auxiliary.loc[auxiliary["detected_pattern"] == pattern]
        shape = z["shape_7d"] <= float(rule["shape_threshold"]) if pattern == "FAN_IN" else z["shape_7d"] >= float(rule["shape_threshold"])
        if rule["rule_type"] == "two_of_four_points":
            points = (
                (z["degree_7d"] >= int(rule["degree_threshold"])).astype(int)
                + (z["tx_count_7d"] >= int(rule["tx_count_threshold"])).astype(int)
                + (z["counterparty_day_concentration"] <= float(rule["max_counterparty_day_concentration"])).astype(int)
                + shape.astype(int)
            )
            hits.append(z.loc[points >= int(rule["min_points"])] .assign(signal_points=points[points >= int(rule["min_points"]) ]))
        elif rule["rule_type"] == "degree_shape":
            hits.append(z.loc[(z["degree_7d"] >= int(rule["degree_threshold"])) & shape])
        else:
            raise ValueError(f"unknown rule_type for {pattern}: {rule['rule_type']}")
    return pd.concat(hits, ignore_index=True) if hits else auxiliary.iloc[0:0].copy()


def detect_fan_v3_min(
    auxiliary: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    splits: list[str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    df = auxiliary if splits is None else auxiliary.loc[auxiliary["sample_split"].isin(splits)]
    selected = select_fan_v3_min_hits(df, config)
    det_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for pattern, key in (("FAN_IN", "fan_in"), ("FAN_OUT", "fan_out")):
        hits = selected.loc[selected["detected_pattern"] == pattern].copy()
        if hits.empty:
            continue
        # Reuse the stable artifact emitter while retaining all v3 auxiliary metrics.
        hits["in_degree_7d"] = hits["degree_7d"]
        hits["out_degree_7d"] = hits["degree_7d"]
        hits["inflow_concentration_7d"] = hits["shape_7d"]
        hits["outflow_dispersion_7d"] = hits["shape_7d"]
        metric_cols = ["degree_7d", "tx_count_7d", "counterparty_day_concentration", "shape_7d"]
        if "signal_points" in hits.columns:
            metric_cols.append("signal_points")
        d, e = _emit_pattern_rows(
            hits,
            pattern=pattern,
            version=str(config["detector_version"]),
            metric_cols=metric_cols,
            threshold_metrics={"rule": dict(config[key])},
        )
        det_rows.extend(d)
        evidence.extend(e)
    detections = pd.DataFrame(det_rows, columns=list(DETECTION_COLUMNS))
    if not detections.empty:
        detections = detections.sort_values(["as_of_ts", "detected_pattern", "account_key"], kind="mergesort").reset_index(drop=True)
    return detections, evidence


def _sha1_16(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_fan_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def pattern_instance_id_fan(
    *,
    detected_pattern: str,
    account_key: str,
    as_of_ts: pd.Timestamp,
    detector_version: str,
    window: str = WINDOW_7D,
) -> str:
    as_of = parse_utc(as_of_ts).isoformat()
    key = "|".join([as_of, window, detector_version, detected_pattern, account_key])
    return f"PI_{detected_pattern}_{_sha1_16(key)}"


def evidence_id_fan(pi: str) -> str:
    return f"EV_{_sha1_16(pi)}"


def detection_id_fan(pi: str, account_key: str) -> str:
    return f"DET_{_sha1_16(pi + '|' + account_key)}"


def _emit_pattern_rows(
    hits: pd.DataFrame,
    *,
    pattern: str,
    version: str,
    metric_cols: list[str],
    threshold_metrics: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    det_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    if hits.empty:
        return det_rows, evidence

    for rec in hits.to_dict(orient="records"):
        account = str(rec["account_key"])
        as_of = parse_utc(rec["as_of_ts"])
        snap = rec["snapshot_date"]
        snap_s = snap.isoformat() if hasattr(snap, "isoformat") else str(snap)
        window = str(rec.get("window") or WINDOW_7D)
        sample_split = str(rec["sample_split"])
        pi = pattern_instance_id_fan(
            detected_pattern=pattern,
            account_key=account,
            as_of_ts=as_of,
            detector_version=version,
            window=window,
        )
        ev = evidence_id_fan(pi)
        metrics = {c: rec[c] for c in metric_cols}
        metrics.update(threshold_metrics)
        # normalize numeric types
        for k, v in list(metrics.items()):
            if hasattr(v, "item"):
                metrics[k] = v.item()
            elif isinstance(v, (pd.Timestamp,)):
                metrics[k] = str(v)

        det_rows.append(
            {
                "detection_id": detection_id_fan(pi, account),
                "pattern_instance_id": pi,
                "evidence_id": ev,
                "account_key": account,
                "as_of_ts": as_of,
                "snapshot_date": snap,
                "window": window,
                "sample_split": sample_split,
                "detected_pattern": pattern,
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
                "detected_pattern": pattern,
                "detector_version": version,
                "accounts": [account],
                "transaction_ids": [],
                "hops": [],
                "metrics": metrics,
                "cycle_length": None,
                "duration_hours": None,
            }
        )
    return det_rows, evidence


def detect_fan_from_features(
    features: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    *,
    splits: list[str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Emit FAN_IN / FAN_OUT detections + evidence from feature rows.

    One hit → one pattern_instance_id, one evidence_id, one detection_id (center).
    Does not use new_* or label_*.
    """
    cfg = dict(config) if config is not None else load_fan_config()
    version = str(cfg["detector_version"])
    required = {
        "account_key",
        "as_of_ts",
        "snapshot_date",
        "window",
        "sample_split",
        "in_degree_7d",
        "out_degree_7d",
        "inflow_concentration_7d",
        "outflow_dispersion_7d",
    }
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"features missing columns: {sorted(missing)}")

    df = features.copy()
    df["as_of_ts"] = pd.to_datetime(df["as_of_ts"], utc=True)
    if splits is not None:
        df = df.loc[df["sample_split"].isin(splits)]

    fi = cfg["fan_in"]
    fo = cfg["fan_out"]
    fan_in_hits = df.loc[
        (df["in_degree_7d"] >= int(fi["min_in_degree_7d"]))
        & (df["inflow_concentration_7d"] <= float(fi["max_inflow_concentration_7d"]))
    ]
    fan_out_hits = df.loc[
        (df["out_degree_7d"] >= int(fo["min_out_degree_7d"]))
        & (df["outflow_dispersion_7d"] >= float(fo["min_outflow_dispersion_7d"]))
    ]

    det_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    d1, e1 = _emit_pattern_rows(
        fan_in_hits,
        pattern="FAN_IN",
        version=version,
        metric_cols=["in_degree_7d", "inflow_concentration_7d"],
        threshold_metrics={
            "min_in_degree_7d": fi["min_in_degree_7d"],
            "max_inflow_concentration_7d": fi["max_inflow_concentration_7d"],
        },
    )
    d2, e2 = _emit_pattern_rows(
        fan_out_hits,
        pattern="FAN_OUT",
        version=version,
        metric_cols=["out_degree_7d", "outflow_dispersion_7d"],
        threshold_metrics={
            "min_out_degree_7d": fo["min_out_degree_7d"],
            "min_outflow_dispersion_7d": fo["min_outflow_dispersion_7d"],
        },
    )
    det_rows.extend(d1)
    det_rows.extend(d2)
    evidence.extend(e1)
    evidence.extend(e2)

    detections = pd.DataFrame(det_rows, columns=list(DETECTION_COLUMNS))
    if not detections.empty:
        detections = detections.sort_values(
            ["as_of_ts", "detected_pattern", "account_key"], kind="mergesort"
        ).reset_index(drop=True)
    assert_no_label_leakage(list(detections.columns))
    return detections, evidence


def _fan_witnesses_from_frame(
    detections: pd.DataFrame, transactions: pd.DataFrame
) -> dict[str, list[dict[str, Any]]]:
    """Pick one deterministic, largest-amount witness per FAN counterparty."""
    tx = transactions.copy()
    required = {
        "transaction_id", "occurred_at", "from_account_key", "to_account_key",
        "amount", "amount_received",
    }
    missing = required - set(tx.columns)
    if missing:
        raise ValueError(f"transactions missing columns: {sorted(missing)}")
    tx["occurred_at"] = pd.to_datetime(tx["occurred_at"], utc=True)
    out: dict[str, list[dict[str, Any]]] = {}
    for det in detections.to_dict(orient="records"):
        end = parse_utc(det["as_of_ts"])
        start = end - pd.Timedelta(days=7)
        center = str(det["account_key"])
        if det["detected_pattern"] == "FAN_IN":
            rows = tx.loc[
                (tx["occurred_at"] >= start) & (tx["occurred_at"] < end)
                & (tx["to_account_key"].astype(str) == center)
            ].copy()
            rows["counterparty"] = rows["from_account_key"].astype(str)
            rows["witness_amount"] = pd.to_numeric(rows["amount_received"])
        else:
            rows = tx.loc[
                (tx["occurred_at"] >= start) & (tx["occurred_at"] < end)
                & (tx["from_account_key"].astype(str) == center)
            ].copy()
            rows["counterparty"] = rows["to_account_key"].astype(str)
            rows["witness_amount"] = pd.to_numeric(rows["amount"])
        rows["transaction_id"] = rows["transaction_id"].astype(str)
        rows = rows.sort_values(
            ["counterparty", "witness_amount", "occurred_at", "transaction_id"],
            ascending=[True, False, True, True], kind="mergesort",
        ).drop_duplicates("counterparty", keep="first")
        out[str(det["evidence_id"])] = [_witness_record(r) for r in rows.to_dict("records")]
    return out


def _witness_record(rec: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "transaction_id": str(rec["transaction_id"]),
        "occurred_at": parse_utc(rec["occurred_at"]).isoformat(),
        "from_account_key": str(rec["from_account_key"]),
        "to_account_key": str(rec["to_account_key"]),
        "amount": float(rec["amount"]),
        "amount_received": float(rec["amount_received"]),
    }
    if "channel" in rec and pd.notna(rec["channel"]):
        result["channel"] = str(rec["channel"])
    return result


def _fan_witnesses_from_duckdb(
    detections: pd.DataFrame, duckdb_path: str | Path
) -> dict[str, list[dict[str, Any]]]:
    if detections.empty:
        return {}
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{Path(duckdb_path).resolve().as_posix()}' AS aml (READ_ONLY)")
        con.register("fan_detections", detections)
        rows = con.execute(
            """
            WITH candidates AS (
              SELECT d.evidence_id, d.detected_pattern, d.account_key,
                     d.as_of_ts - INTERVAL 7 DAY AS start_ts, d.as_of_ts AS end_ts
              FROM fan_detections d
            ), edges AS (
              SELECT c.evidence_id, t.from_account_key AS counterparty,
                     CAST(t.transaction_id AS VARCHAR) AS transaction_id,
                     t.occurred_at, t.from_account_key, t.to_account_key,
                     t.amount, t.amount_received, t.channel,
                     t.amount_received AS witness_amount
              FROM candidates c
              JOIN aml.transaction t
                ON c.detected_pattern = 'FAN_IN'
               AND t.to_account_key = c.account_key
               AND t.occurred_at >= c.start_ts AND t.occurred_at < c.end_ts
              UNION ALL
              SELECT c.evidence_id, t.to_account_key AS counterparty,
                     CAST(t.transaction_id AS VARCHAR) AS transaction_id,
                     t.occurred_at, t.from_account_key, t.to_account_key,
                     t.amount, t.amount_received, t.channel,
                     t.amount AS witness_amount
              FROM candidates c
              JOIN aml.transaction t
                ON c.detected_pattern = 'FAN_OUT'
               AND t.from_account_key = c.account_key
               AND t.occurred_at >= c.start_ts AND t.occurred_at < c.end_ts
            ), ranked AS (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY evidence_id, counterparty
                ORDER BY witness_amount DESC, occurred_at, transaction_id
              ) AS rn
              FROM edges
            )
            SELECT * EXCLUDE (counterparty, witness_amount, rn)
            FROM ranked WHERE rn = 1
            ORDER BY evidence_id, occurred_at, transaction_id
            """
        ).fetchdf()
    finally:
        con.close()
    out: dict[str, list[dict[str, Any]]] = {}
    for rec in rows.to_dict(orient="records"):
        out.setdefault(str(rec.pop("evidence_id")), []).append(_witness_record(rec))
    return out


def hydrate_fan_evidence(
    detections: pd.DataFrame,
    evidence: list[dict[str, Any]],
    *,
    transactions: pd.DataFrame | None = None,
    duckdb_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Attach traceable TX witnesses; one largest TX per unique counterparty."""
    if transactions is not None:
        witness_map = _fan_witnesses_from_frame(detections, transactions)
    elif duckdb_path is not None:
        witness_map = _fan_witnesses_from_duckdb(detections, duckdb_path)
    else:
        raise ValueError("provide transactions= or duckdb_path=")
    hydrated: list[dict[str, Any]] = []
    for original in evidence:
        rec = dict(original)
        hops = witness_map.get(str(rec["evidence_id"]), [])
        if not hops:
            raise ValueError(f"no transaction witness for evidence_id={rec['evidence_id']}")
        center = rec["accounts"][0]
        counterparties = {
            h["from_account_key"] if rec["detected_pattern"] == "FAN_IN"
            else h["to_account_key"] for h in hops
        }
        rec["accounts"] = [center] + sorted(counterparties)
        rec["transaction_ids"] = [h["transaction_id"] for h in hops]
        rec["hops"] = hops
        rec["evidence_policy"] = "largest_transaction_per_counterparty_v1"
        rec["witness_counterparty_count"] = len(counterparties)
        hydrated.append(rec)
    return hydrated


def write_fan_artifacts(
    detections: pd.DataFrame,
    evidence: list[dict[str, Any]],
    *,
    detection_path: str | Path,
    evidence_path: str | Path,
    merge_non_fan: bool = True,
) -> None:
    """Write FAN detections/evidence; optionally keep non-FAN rows already on disk."""
    detection_path = Path(detection_path)
    evidence_path = Path(evidence_path)
    detection_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    if merge_non_fan and detection_path.exists():
        existing = pd.read_parquet(detection_path)
        keep = existing.loc[~existing["detected_pattern"].isin(FAN_PATTERNS)]
        combined = pd.concat([keep, detections], ignore_index=True)
    else:
        combined = detections.copy()
    if not combined.empty:
        combined["snapshot_date"] = pd.to_datetime(combined["snapshot_date"]).dt.date
        combined = combined.sort_values(
            ["as_of_ts", "detected_pattern", "account_key"], kind="mergesort"
        ).reset_index(drop=True)
    combined.to_parquet(detection_path, index=False)

    existing_ev: list[dict[str, Any]] = []
    if merge_non_fan and evidence_path.exists():
        with evidence_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("detected_pattern") not in FAN_PATTERNS:
                    existing_ev.append(rec)
    combined_ev = existing_ev + evidence
    with evidence_path.open("w", encoding="utf-8") as f:
        for rec in combined_ev:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def run_fan_detector(
    *,
    features_path: str | Path,
    config_path: str | Path | None = None,
    detection_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
    duckdb_path: str | Path | None = None,
    splits: list[str] | None = None,
    merge_non_fan: bool = True,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    cfg = load_fan_config(config_path)
    features = pd.read_parquet(features_path)
    if str(cfg.get("detector_version", "")).startswith("graph_fan_v3"):
        if duckdb_path is None:
            raise ValueError("graph_fan_v3 requires duckdb_path")
        scoped = features if splits is None else features.loc[features["sample_split"].isin(splits)]
        auxiliary = compute_fan_auxiliary_duckdb(
            scoped, duckdb_path=duckdb_path, min_degree=int(cfg["candidate_min_degree"])
        )
        detections, evidence = detect_fan_v3_min(auxiliary, cfg, splits=splits)
    else:
        detections, evidence = detect_fan_from_features(features, cfg, splits=splits)
    if duckdb_path is not None:
        evidence = hydrate_fan_evidence(
            detections, evidence, duckdb_path=duckdb_path
        )
    if detection_path is not None and evidence_path is not None:
        write_fan_artifacts(
            detections,
            evidence,
            detection_path=detection_path,
            evidence_path=evidence_path,
            merge_non_fan=merge_non_fan,
        )
    return detections, evidence
