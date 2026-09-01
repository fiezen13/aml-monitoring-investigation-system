#!/usr/bin/env python3
"""Batch-score native-currency transactions with the frozen FIN-07 joblib bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.currency_native_edge import (  # noqa: E402
    MODEL_VERSION,
    load_bundle,
    load_split,
    prepare_feature_tables,
    sha256_file,
)

DEFAULT_DB = ROOT / "data/processed/aml.duckdb"
DEFAULT_MODEL = ROOT / "models/fin07_currency_native_policy_edge_li_small_v1.joblib"
DEFAULT_OUTPUT = ROOT / "data/processed/edge-policy-v1/li_small_batch_scores.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--split", choices=("train", "val", "test"), default="test")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="18GB")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise FileNotFoundError(args.db)
    if not args.model.exists():
        raise FileNotFoundError(args.model)

    bundle = load_bundle(args.model)
    protocol = bundle["protocol"]
    window_days = int(protocol["window_days"])
    degree_cap = int(protocol["degree_cap"])

    print(f"[1/3] Rebuilding causal native features for split={args.split}", flush=True)
    connection = duckdb.connect(str(args.db), read_only=True)
    try:
        connection.execute("SET TimeZone='UTC'")
        connection.execute(f"SET threads={int(args.threads)}")
        connection.execute(f"SET memory_limit='{args.memory_limit}'")
        connection.execute("SET preserve_insertion_order=false")
        _, data_report = prepare_feature_tables(
            connection,
            window_days=window_days,
            degree_cap=degree_cap,
            preprocessing=bundle["preprocessing"],
        )
        matrix, target, metadata = load_split(connection, args.split, include_metadata=True)
    finally:
        connection.close()
    if metadata is None:
        raise RuntimeError("audit metadata was not returned")
    if len(target) == 0:
        raise ValueError(f"split={args.split} contains no transactions")

    print("[2/3] Scoring frozen joblib model", flush=True)
    score = bundle["model"].predict_proba(matrix)[:, 1]
    threshold = float(bundle["threshold"])
    output = metadata.copy()
    output["target_laundering"] = target
    output["score"] = score
    output["threshold"] = threshold
    output["triggered"] = score >= threshold
    output["model_version"] = bundle["model_version"]
    output["scored_at"] = datetime.now(UTC)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)
    summary_path = args.summary_out or args.output.with_suffix(".summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "fin07.currency_native_edge.scoring.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "model_version": bundle["model_version"],
        "expected_model_version": MODEL_VERSION,
        "split": args.split,
        "rows": int(len(output)),
        "alerts": int(output["triggered"].sum()),
        "alert_rate": float(output["triggered"].mean()),
        "threshold": threshold,
        "uses_static_fx": False,
        "preserved_audit_fields": [
            "amount_paid_orig",
            "payment_currency",
            "amount_received_orig",
            "receiving_currency",
        ],
        "score_min": float(np.min(score)),
        "score_max": float(np.max(score)),
        "data_quality": data_report,
        "artifacts": {
            "model": {"path": str(args.model), "sha256": sha256_file(args.model)},
            "scores": {"path": str(args.output), "sha256": sha256_file(args.output)},
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"  scores  -> {args.output}", flush=True)
    print(f"  summary -> {summary_path}", flush=True)
    print("[3/3] Complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
