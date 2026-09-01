#!/usr/bin/env python3
"""Evaluate FAN_IN / FAN_OUT / GATHER_SCATTER vs IBM Patterns.txt (test P/R/F1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.graph_detector_eval import (  # noqa: E402
    run_graph_detector_eval,
    write_eval_report,
)


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 Graph detector eval vs IBM GT")
    parser.add_argument(
        "--patterns",
        type=Path,
        default=ROOT / "data/raw/ibm-aml/LI-Small_Patterns.txt",
    )
    parser.add_argument(
        "--detections",
        type=Path,
        default=ROOT / "data/processed/graph_detection_v1.parquet",
    )
    parser.add_argument(
        "--split-cutoffs",
        type=Path,
        default=ROOT / "data/processed/split_cutoffs.json",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "data/processed/graph_evidence_v1.jsonl",
        help="Evidence JSONL used for optional CYCLE evaluation",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=ROOT / "reports/graph_eval_v2.json",
    )
    parser.add_argument(
        "--gt-out",
        type=Path,
        default=ROOT / "data/processed/ibm_graph_eval_gt_v1.json",
    )
    parser.add_argument("--primary-split", default="test")
    parser.add_argument(
        "--eval-version",
        default="graph_eval_v2",
        help="Label written into report eval_version field",
    )
    args = parser.parse_args()

    report = run_graph_detector_eval(
        patterns_path=args.patterns,
        detection_path=args.detections,
        split_cutoffs_path=args.split_cutoffs,
        primary_split=args.primary_split,
        evidence_path=args.evidence,
    )
    report["eval_version"] = args.eval_version
    write_eval_report(report, report_path=args.report_out, gt_out_path=args.gt_out)

    primary = report["primary"]
    overall = primary["overall"]
    print(
        f"OK: wrote {args.report_out} gt={args.gt_out} "
        f"primary={args.primary_split} "
        f"P={_fmt(overall['precision'])} R={_fmt(overall['recall'])} "
        f"F1={_fmt(overall['f1'])} "
        f"gt={overall['n_gt']} pred={overall['n_pred']} "
        f"gt_hit={overall['n_gt_hit']} pred_hit={overall['n_pred_hit']}"
    )
    for pat, m in primary["by_pattern"].items():
        print(
            f"  {pat}: P={_fmt(m['precision'])} R={_fmt(m['recall'])} "
            f"F1={_fmt(m['f1'])} gt={m['n_gt']} pred={m['n_pred']}"
        )
    cycle = report["cycle_evaluation"]["primary"]
    print(
        f"  CYCLE: status={cycle['status']} P={_fmt(cycle['precision'])} "
        f"R={_fmt(cycle['recall'])} F1={_fmt(cycle['f1'])} "
        f"gt={cycle['n_gt']} pred={cycle['n_pred']} "
        f"gt_hit={cycle['n_gt_hit']} pred_hit={cycle['n_pred_hit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
