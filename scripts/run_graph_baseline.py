#!/usr/bin/env python3
"""Build the graph account modeling table and run frozen classical baselines."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.graph_baseline import (  # noqa: E402
    DETECTOR_FEATURE_COLUMNS,
    GRAPH_FEATURE_COLUMNS,
    ID_COLUMNS,
    TARGET_COLUMN,
    build_modeling_table,
    run_baselines,
    sha256_file,
    write_report,
)


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Graph account baseline modeling")
    parser.add_argument("--db", type=Path, default=ROOT / "data/processed/aml.duckdb")
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "data/processed/graph_features_v1.parquet",
    )
    parser.add_argument(
        "--detections",
        type=Path,
        default=ROOT / "data/processed/graph_detection_v1.parquet",
    )
    parser.add_argument(
        "--modeling-out",
        type=Path,
        default=ROOT / "data/processed/graph_account_modeling_v1.parquet",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=ROOT / "reports/graph_account_baseline_v1.json",
    )
    parser.add_argument("--precision-k", type=int, default=1000)
    parser.add_argument("--alert-budget-rate", type=float, default=0.01)
    args = parser.parse_args()

    started = time.perf_counter()
    print("[1/3] Building current-window modeling table", flush=True)
    table_meta = build_modeling_table(
        args.db, args.features, args.detections, args.modeling_out
    )
    print(json.dumps(table_meta["row_counts"], indent=2), flush=True)
    print(f"modeling_table_rss_mb={rss_mb():.1f}", flush=True)

    print("[2/3] Fit=train; selection=validation", flush=True)
    baseline = run_baselines(
        args.modeling_out,
        precision_k=args.precision_k,
        alert_budget_rate=args.alert_budget_rate,
    )
    print("[3/3] Final test pass complete", flush=True)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "artifacts": {
            "input_db": str(args.db),
            "graph_features": str(args.features),
            "graph_features_sha256": sha256_file(args.features),
            "graph_detections": str(args.detections),
            "graph_detections_sha256": sha256_file(args.detections),
            "modeling_table": str(args.modeling_out),
            "modeling_table_sha256": table_meta["output_sha256"],
        },
        "modeling_table": {
            **table_meta,
            "schema": {
                "identifiers": ID_COLUMNS,
                "graph_features": GRAPH_FEATURE_COLUMNS,
                "detector_features": DETECTOR_FEATURE_COLUMNS,
                "target": TARGET_COLUMN,
            },
        },
        "baseline": baseline,
        "total_runtime_seconds": time.perf_counter() - started,
        "peak_rss_mb": rss_mb(),
    }
    write_report(report, args.report_out)
    print(f"report={args.report_out}", flush=True)
    print(f"peak_rss_mb={rss_mb():.1f}", flush=True)
    print(f"total_runtime_seconds={report['total_runtime_seconds']:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
