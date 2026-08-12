#!/usr/bin/env python3
"""Run one graph detector phase in an isolated process."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.cycle_detector import run_cycle_detector  # noqa: E402
from src.data.fan_detector import run_fan_detector  # noqa: E402
from src.data.gather_scatter_detector import run_gather_scatter_detector  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("fan", "gather", "cycle"))
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--cutoffs", type=Path, required=True)
    p.add_argument("--config", type=Path, required=False)
    p.add_argument("--detection-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    args = p.parse_args()
    args.detection_out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if args.phase == "fan":
        det, ev = run_fan_detector(
            features_path=args.features, config_path=args.config,
            detection_path=args.detection_out, evidence_path=args.evidence_out,
            duckdb_path=args.db, splits=["train", "val", "test"],
            merge_non_fan=False,
        )
    elif args.phase == "gather":
        det, ev = run_gather_scatter_detector(
            features_path=args.features, duckdb_path=args.db, config_path=args.config,
            detection_path=args.detection_out, evidence_path=args.evidence_out,
            splits=["train", "val", "test"], merge_existing=False,
        )
    else:
        det, ev = run_cycle_detector(
            db_path=args.db, cutoffs_path=args.cutoffs,
            detection_path=args.detection_out, evidence_path=args.evidence_out,
        )
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    print(json.dumps({
        "phase": args.phase, "runtime_s": round(time.perf_counter() - t0, 3),
        "peak_rss_mb": round(rss, 1), "detection_rows": int(len(det)),
        "evidence_rows": len(ev),
    }), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
