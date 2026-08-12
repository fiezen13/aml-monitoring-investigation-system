#!/usr/bin/env python3
"""Canonical graph production runner: features → detectors → validate → manifest."""

from __future__ import annotations

import hashlib
import json
import resource
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.cycle_detector import write_cycle_artifacts  # noqa: E402
from src.data.fan_detector import run_fan_detector  # noqa: E402
from src.data.gather_scatter_detector import detect_gather_scatter, load_gather_config  # noqa: E402
from src.data.graph_artifact_validator import validate_graph_artifacts  # noqa: E402
from src.data.snapshot_split import load_split_cutoffs  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    db = ROOT / "data/processed/aml.duckdb"
    features_path = ROOT / "data/processed/graph_features_v1.parquet"
    cutoffs_path = ROOT / "data/processed/split_cutoffs.json"
    fan_cfg = ROOT / "configs/graph/graph_fan_config_v3.json"
    gather_cfg = ROOT / "configs/graph/graph_gather_config_v1.json"
    detection_path = ROOT / "data/processed/graph_detection_v1.parquet"
    evidence_path = ROOT / "data/processed/graph_evidence_v1.jsonl"
    manifest_path = ROOT / "reports/graph_pipeline_manifest_v1.json"
    t0 = time.perf_counter()
    features = pd.read_parquet(features_path)
    splits = ["train", "val", "test"]
    fan_det, fan_ev = run_fan_detector(
        features_path=features_path, config_path=fan_cfg, duckdb_path=db,
        splits=splits, merge_non_fan=False,
    )
    gather_det, gather_ev = detect_gather_scatter(
        features, duckdb_path=db, config=load_gather_config(gather_cfg), splits=splits
    )
    # CYCLE reads the canonical DB directly; use its existing runner path.
    from src.data.cycle_detector import run_cycle_detector
    cycle_det, cycle_ev = run_cycle_detector(db_path=db, cutoffs_path=cutoffs_path)
    all_det = pd.concat([fan_det, gather_det, cycle_det], ignore_index=True)
    all_det = all_det.sort_values(["as_of_ts", "detected_pattern", "account_key"], kind="mergesort").reset_index(drop=True)
    all_ev = fan_ev + gather_ev + cycle_ev
    write_cycle_artifacts(all_det, all_ev, detection_path=detection_path, evidence_path=evidence_path)
    validation = validate_graph_artifacts(detection_path, evidence_path, db_path=db)
    configs = {str(p.relative_to(ROOT)): sha256(p) for p in (fan_cfg, gather_cfg)}
    manifest = {
        "manifest_version": "graph_pipeline_manifest_v1",
        "input_db_checksum": sha256(db),
        "feature_artifact_checksum": sha256(features_path),
        "feature_schema_version": "graph_features_v1",
        "detector_versions": {p: sorted(set(all_det.loc[all_det.detected_pattern == p, "detector_version"].astype(str))) for p in all_det.detected_pattern.unique()},
        "config_hashes": configs,
        "snapshot_range": {
            "min": str(pd.to_datetime(all_det.snapshot_date).min().date()),
            "max": str(pd.to_datetime(all_det.snapshot_date).max().date()),
        },
        "row_counts": {"detections": len(all_det), "evidence": len(all_ev), "by_pattern": all_det.detected_pattern.value_counts().to_dict()},
        "validation": validation,
        "runtime_s": round(time.perf_counter() - t0, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "test_status": "PASS" if validation["status"] == "PASS" else "FAIL",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if validation["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
