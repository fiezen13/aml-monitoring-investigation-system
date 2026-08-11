#!/usr/bin/env python3
"""Run GATHER_SCATTER detector and merge into graph_detection/evidence v1."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.gather_scatter_detector import run_gather_scatter_detector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 GATHER_SCATTER detector")
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "data/processed/graph_features_v1.parquet",
    )
    parser.add_argument(
        "--duckdb",
        type=Path,
        default=ROOT / "data/processed/aml.duckdb",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/graph/graph_gather_config_v1.json",
    )
    parser.add_argument(
        "--detection-out",
        type=Path,
        default=ROOT / "data/processed/graph_detection_v1.parquet",
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        default=ROOT / "data/processed/graph_evidence_v1.jsonl",
    )
    parser.add_argument(
        "--splits",
        default="train,val,test",
        help="Comma-separated sample_split values to emit",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Overwrite outputs with GATHER-only (default: merge into existing)",
    )
    args = parser.parse_args()
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]

    t0 = time.perf_counter()
    det, ev = run_gather_scatter_detector(
        features_path=args.features,
        duckdb_path=args.duckdb,
        config_path=args.config,
        detection_path=args.detection_out,
        evidence_path=args.evidence_out,
        splits=splits,
        merge_existing=not args.no_merge,
    )
    elapsed = time.perf_counter() - t0
    gather_n = (
        int((det["detected_pattern"] == "GATHER_SCATTER").sum()) if len(det) else 0
    )
    print(
        f"OK: total_detections={len(det)} total_evidence={len(ev)} "
        f"gather_scatter={gather_n} runtime_s={elapsed:.2f} "
        f"patterns={det['detected_pattern'].value_counts().to_dict() if len(det) else {}} "
        f"splits={det['sample_split'].value_counts().to_dict() if len(det) else {}}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
