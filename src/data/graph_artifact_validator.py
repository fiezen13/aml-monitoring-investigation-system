"""Shared validation for merged graph detection/evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import assign_snapshot_split, load_split_cutoffs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_graph_artifacts(
    detection_path: str | Path,
    evidence_path: str | Path,
    *,
    db_path: str | Path | None = None,
    feature_path: str | Path | None = None,
    split_cutoffs_path: str | Path | None = None,
    expected_detector_versions: Mapping[str, str] | None = None,
    config_hashes: Mapping[str, str] | None = None,
    config_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Validate graph artifact identity, joins, splits, windows and leakage."""
    det = pd.read_parquet(detection_path)
    evidence = [
        json.loads(line) for line in Path(evidence_path).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    errors: list[str] = []
    assert_no_label_leakage(list(det.columns))
    if split_cutoffs_path is not None:
        cutoffs = load_split_cutoffs(split_cutoffs_path)
        expected_splits = [assign_snapshot_split(value, cutoffs) for value in det["as_of_ts"]]
        bad_split = sum(
            str(actual) != expected for actual, expected in zip(det["sample_split"], expected_splits, strict=True)
        )
        if bad_split:
            errors.append(f"sample_split mismatch: {bad_split} detection rows")

    if expected_detector_versions:
        for pattern, expected in expected_detector_versions.items():
            det_versions = set(det.loc[det["detected_pattern"] == pattern, "detector_version"].dropna().astype(str))
            if det_versions and det_versions != {expected}:
                errors.append(
                    f"detector version mismatch for {pattern}: expected={expected} actual={sorted(det_versions)}"
                )

    if config_hashes is not None:
        if config_paths is None:
            errors.append("config paths missing for config hash validation")
        else:
            for name, expected in config_hashes.items():
                path = config_paths.get(name)
                if path is None or not Path(path).exists():
                    errors.append(f"config missing for hash validation: {name}")
                    continue
                actual = _sha256(Path(path))
                if actual != expected:
                    errors.append(f"config hash mismatch for {name}: expected={expected} actual={actual}")

    if feature_path is not None:
        feature = Path(feature_path)
        if not feature.exists():
            errors.append(f"feature artifact missing: {feature}")
        else:
            con = duckdb.connect()
            try:
                feature_sql = _sql_path(feature)
                detection_sql = _sql_path(Path(detection_path))
                join = (
                    "d.account_key = f.account_key AND d.as_of_ts = f.as_of_ts "
                    'AND d.snapshot_date = f.snapshot_date AND d."window" = f."window"'
                )
                bad_join = con.execute(
                    f"""
                    SELECT COUNT(*) FROM (
                      SELECT d.detection_id, COUNT(f.account_key) AS n
                      FROM read_parquet('{detection_sql}') d
                      LEFT JOIN read_parquet('{feature_sql}') f ON {join}
                      GROUP BY d.detection_id
                      HAVING n <> 1
                    )
                    """
                ).fetchone()[0]
                if bad_join:
                    errors.append(f"detection-feature join cardinality mismatch: {bad_join} rows")
                bad_feature_split = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM read_parquet('{detection_sql}') d
                    JOIN read_parquet('{feature_sql}') f ON {join}
                    WHERE d.sample_split <> f.sample_split
                    """
                ).fetchone()[0]
                if bad_feature_split:
                    errors.append(f"detection-feature sample_split mismatch: {bad_feature_split} rows")
                schema_values = [
                    str(row[0])
                    for row in con.execute(
                        f"SELECT DISTINCT feature_schema_version FROM read_parquet('{feature_sql}')"
                    ).fetchall()
                ]
                if schema_values != ["graph_features_v1"]:
                    errors.append(f"feature schema mismatch: expected=['graph_features_v1'] actual={schema_values}")
            finally:
                con.close()
    if det["detection_id"].duplicated().any():
        errors.append("duplicate detection_id")
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    evidence_by_pi = {row["pattern_instance_id"]: row for row in evidence}
    if len(evidence_by_id) != len(evidence):
        errors.append("duplicate evidence_id")
    if len(evidence_by_pi) != len(evidence):
        errors.append("duplicate pattern_instance_id")
    if set(det["evidence_id"]) - set(evidence_by_id):
        errors.append("detection references missing evidence")
    if set(det["pattern_instance_id"]) - set(evidence_by_pi):
        errors.append("detection references missing pattern evidence")
    if set(evidence_by_pi) - set(det["pattern_instance_id"]):
        errors.append("orphan evidence")

    tx_ids: set[str] = set()
    fan_refs: list[tuple[str, str, str, str, pd.Timestamp, pd.Timestamp]] = []
    gather_refs: list[tuple[str, str, str, str, set[str], set[str], pd.Timestamp, pd.Timestamp]] = []
    witness_rows = 0
    for row in evidence:
        as_of = pd.Timestamp(row["as_of_ts"])
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize("UTC")
        else:
            as_of = as_of.tz_convert("UTC")
        start, end = as_of - pd.Timedelta(days=7), as_of
        pattern = row.get("detected_pattern")
        linked = det.loc[det["evidence_id"] == row["evidence_id"]]
        if not linked.empty:
            for field in ("sample_split", "detected_pattern", "detector_version", "window"):
                if set(linked[field].astype(str)) != {str(row.get(field))}:
                    errors.append(f"detection-evidence {field} mismatch: {row['pattern_instance_id']}")
        if pattern == "CYCLE":
            accounts = row.get("accounts", [])
            hops = row.get("hops", [])
            if len(hops) != len(accounts):
                errors.append(f"CYCLE hop/account length mismatch: {row['pattern_instance_id']}")
            for i, hop in enumerate(hops):
                next_hop = hops[(i + 1) % len(hops)] if hops else hop
                if hop.get("to_account_key") != next_hop.get("from_account_key"):
                    errors.append(f"CYCLE hop continuity: {row['pattern_instance_id']}")
                ts = pd.Timestamp(hop["occurred_at"])
                if not (start <= ts < end):
                    errors.append(f"transaction outside window: {hop.get('transaction_id')}")
                tx_ids.add(str(hop["transaction_id"]))
                witness_rows += 1
            times = [pd.Timestamp(h["occurred_at"]) for h in hops]
            if times and any(times[i] > times[i + 1] for i in range(len(times) - 1)):
                errors.append(f"CYCLE witness not temporal: {row['pattern_instance_id']}")
        elif pattern == "GATHER_SCATTER":
            centers = set(linked["account_key"].astype(str))
            if len(centers) != 1:
                errors.append(f"GATHER center cardinality: {row['pattern_instance_id']}")
            center = next(iter(centers), "")
            sources = set(str(x) for x in row.get("sources", []) or [])
            destinations = set(str(x) for x in row.get("destinations", []) or [])
            gather_ids = [str(x) for x in row.get("gather_transaction_ids", []) or []]
            scatter_ids = [str(x) for x in row.get("scatter_transaction_ids", []) or []]
            if set(gather_ids) & set(scatter_ids):
                errors.append(f"GATHER/SCATTER transaction overlap: {row['pattern_instance_id']}")
            if set(str(x) for x in row.get("transaction_ids", []) or []) != set(gather_ids + scatter_ids):
                errors.append(f"GATHER transaction union mismatch: {row['pattern_instance_id']}")
            for tx_id in gather_ids:
                gather_refs.append((row["evidence_id"], tx_id, "gather", center, sources, destinations, start, end))
                tx_ids.add(tx_id)
                witness_rows += 1
            for tx_id in scatter_ids:
                gather_refs.append((row["evidence_id"], tx_id, "scatter", center, sources, destinations, start, end))
                tx_ids.add(tx_id)
                witness_rows += 1
            continue
        elif pattern in ("FAN_IN", "FAN_OUT"):
            centers = set(linked["account_key"].astype(str))
            if len(centers) != 1:
                errors.append(f"FAN center cardinality: {row['pattern_instance_id']}")
            center = next(iter(centers), "")
            hops = row.get("hops", []) or []
            hop_ids = [str(h.get("transaction_id")) for h in hops]
            evidence_ids = [str(x) for x in row.get("transaction_ids", []) or []]
            if set(hop_ids) != set(evidence_ids):
                errors.append(f"FAN transaction/hops mismatch: {row['pattern_instance_id']}")
            for hop in hops:
                tx_id = str(hop["transaction_id"])
                fan_refs.append((row["evidence_id"], tx_id, pattern, center, start, end))
                tx_ids.add(tx_id)
                witness_rows += 1
            continue
        for key in ("transaction_ids", "gather_transaction_ids", "scatter_transaction_ids"):
            for tx_id in row.get(key, []) or []:
                tx_ids.add(str(tx_id))
                witness_rows += 1

    found = 0
    if db_path and tx_ids:
        con = duckdb.connect(str(db_path), read_only=True)
        frame = pd.DataFrame({"transaction_id": sorted(tx_ids)})
        con.register("graph_validator_tx", frame)
        found = con.execute(
            "SELECT COUNT(*) FROM transaction t JOIN graph_validator_tx x USING (transaction_id)"
        ).fetchone()[0]
        tx_rows = con.execute(
            """
            SELECT t.transaction_id, t.occurred_at, t.from_account_key, t.to_account_key
            FROM transaction t JOIN graph_validator_tx x USING (transaction_id)
            """
        ).fetchall()
        con.close()
        if found != len(tx_ids):
            errors.append(f"missing transaction IDs: expected={len(tx_ids)} found={found}")
        tx_by_id = {str(tx_id): (pd.Timestamp(ts), str(src), str(dst)) for tx_id, ts, src, dst in tx_rows}
        for evidence_id, tx_id, pattern, center, start, end in fan_refs:
            tx = tx_by_id.get(tx_id)
            if tx is None:
                continue
            ts, src, dst = tx
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            if not (start <= ts < end):
                errors.append(f"FAN transaction outside window: {evidence_id}:{tx_id}")
            if pattern == "FAN_IN" and dst != center:
                errors.append(f"FAN_IN direction mismatch: {evidence_id}:{tx_id}")
            if pattern == "FAN_OUT" and src != center:
                errors.append(f"FAN_OUT direction mismatch: {evidence_id}:{tx_id}")
        for evidence_id, tx_id, leg, center, sources, destinations, start, end in gather_refs:
            tx = tx_by_id.get(tx_id)
            if tx is None:
                continue
            ts, src, dst = tx
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            if not (start <= ts < end):
                errors.append(f"GATHER transaction outside window: {evidence_id}:{tx_id}")
            if leg == "gather":
                if dst != center or src not in sources:
                    errors.append(f"GATHER direction mismatch: {evidence_id}:{tx_id}")
            elif src != center or dst not in destinations:
                errors.append(f"SCATTER direction mismatch: {evidence_id}:{tx_id}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "detection_rows": int(len(det)),
        "evidence_rows": len(evidence),
        "unique_detection_ids": int(det["detection_id"].nunique()),
        "unique_evidence_ids": len(evidence_by_id),
        "witness_rows": witness_rows,
        "unique_transaction_ids": len(tx_ids),
        "transaction_ids_found": int(found),
        "feature_join_checked": feature_path is not None,
        "sample_split_checked": split_cutoffs_path is not None,
        "detector_versions_checked": expected_detector_versions is not None,
        "config_hashes_checked": config_hashes is not None,
    }
