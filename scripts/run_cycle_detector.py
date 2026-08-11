#!/usr/bin/env python3
"""Run CYCLE detector (optional ranged smoke — not full by default)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.cycle_detector import run_cycle_detector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 CYCLE detector")
    parser.add_argument("--db", type=Path, default=ROOT / "data/processed/aml.duckdb")
    parser.add_argument(
        "--cutoffs", type=Path, default=ROOT / "data/processed/split_cutoffs.json"
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
    parser.add_argument("--start", default=None, help="UTC date YYYY-MM-DD")
    parser.add_argument("--end-exclusive", default=None, help="UTC date YYYY-MM-DD")
    args = parser.parse_args()

    range_start = (
        datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        if args.start
        else None
    )
    range_end = (
        datetime.fromisoformat(args.end_exclusive).replace(tzinfo=timezone.utc)
        if args.end_exclusive
        else None
    )

    t0 = time.perf_counter()
    det, ev = run_cycle_detector(
        db_path=args.db,
        cutoffs_path=args.cutoffs,
        detection_path=args.detection_out,
        evidence_path=args.evidence_out,
        range_start=range_start,
        range_end_exclusive=range_end,
    )
    elapsed = time.perf_counter() - t0
    print(
        f"OK: detections={len(det)} evidence={len(ev)} "
        f"runtime_s={elapsed:.2f} → {args.detection_out}, {args.evidence_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
