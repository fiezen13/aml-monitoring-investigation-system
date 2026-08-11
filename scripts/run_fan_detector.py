#!/usr/bin/env python3
"""Run FAN_IN/FAN_OUT detectors from graph_features_v1 + frozen config."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.fan_detector import run_fan_detector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 FAN_IN / FAN_OUT detectors")
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "data/processed/aml.duckdb",
        help="Canonical DuckDB used to hydrate transaction-level FAN evidence",
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "data/processed/graph_features_v1.parquet",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/graph/graph_fan_config_v3.json",
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
    args = parser.parse_args()
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]

    t0 = time.perf_counter()
    det, ev = run_fan_detector(
        features_path=args.features,
        config_path=args.config,
        detection_path=args.detection_out,
        evidence_path=args.evidence_out,
        duckdb_path=args.db,
        splits=splits,
    )
    elapsed = time.perf_counter() - t0
    print(
        f"OK: detections={len(det)} evidence={len(ev)} runtime_s={elapsed:.2f} "
        f"patterns={det['detected_pattern'].value_counts().to_dict() if len(det) else {}} "
        f"splits={det['sample_split'].value_counts().to_dict() if len(det) else {}}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
