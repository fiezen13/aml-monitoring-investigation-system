#!/usr/bin/env python3
"""Train and release the currency-native FIN-07 policy edge model on CPU."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_recall_curve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.currency_native_edge import (  # noqa: E402
    ARTIFACT_FORMAT,
    CATEGORICAL_INDICES,
    FEATURE_COLUMNS,
    MODEL_VERSION,
    load_split,
    prepare_feature_tables,
    runtime_metadata,
    sha256_file,
    validate_bundle,
)

DEFAULT_DB = ROOT / "data/processed/hi_medium.duckdb"
DEFAULT_MODEL = ROOT / "models/fin07_currency_native_policy_edge_v1.joblib"
DEFAULT_REPORT = ROOT / "reports/edge-benchmark/hi_medium_currency_native_policy_v1.json"
DEFAULT_SCORES = ROOT / "data/processed/edge-policy-v1/hi_medium_test_scores.parquet"

MODEL_GRID = (
    {"max_iter": 200, "max_leaf_nodes": 31, "learning_rate": 0.1, "class_weight": "balanced"},
    {"max_iter": 500, "max_leaf_nodes": 63, "learning_rate": 0.05, "class_weight": "balanced"},
    {"max_iter": 500, "max_leaf_nodes": 63, "learning_rate": 0.05, "class_weight": None},
    {"max_iter": 800, "max_leaf_nodes": 127, "learning_rate": 0.05, "class_weight": None},
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scores-out", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--degree-cap", type=int, default=200)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="18GB")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 1, 2, 3, 4])
    parser.add_argument("--skip-scores", action="store_true")
    return parser.parse_args()


def best_f1_threshold(y: np.ndarray, score: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y, score)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    return float(thresholds[int(np.argmax(f1[:-1]))])


def metrics(y: np.ndarray, score: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = score >= threshold
    positive = y == 1
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & ~positive))
    fn = int(np.sum(~predicted & positive))
    tn = int(np.sum(~predicted & ~positive))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "rows": int(len(y)),
        "positives": int(positive.sum()),
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": float(average_precision_score(y, score)),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "alerts": tp + fp,
        "alert_rate": float((tp + fp) / len(y)),
    }


def fit_model(config: dict[str, Any], x: np.ndarray, y: np.ndarray, seed: int) -> HistGradientBoostingClassifier:
    model = HistGradientBoostingClassifier(
        learning_rate=config["learning_rate"],
        max_iter=config["max_iter"],
        max_leaf_nodes=config["max_leaf_nodes"],
        min_samples_leaf=50,
        l2_regularization=1.0,
        class_weight=config["class_weight"],
        categorical_features=list(CATEGORICAL_INDICES),
        early_stopping=False,
        random_state=seed,
    )
    model.fit(x, y)
    return model


def operating_points(y: np.ndarray, score: np.ndarray) -> list[dict[str, Any]]:
    order = np.argsort(-score, kind="mergesort")
    positives = int(y.sum())
    rows = []
    for budget in (100, 250, 500, 1000, 2500, 5000, 12239, int(len(y) * 0.01)):
        if budget <= 0 or budget > len(y) or any(row["alerts_reviewed"] == budget for row in rows):
            continue
        caught = int(y[order[:budget]].sum())
        rows.append(
            {
                "alerts_reviewed": budget,
                "caught": caught,
                "false_alarms": budget - caught,
                "precision": float(caught / budget),
                "recall": float(caught / positives) if positives else 0.0,
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise FileNotFoundError(args.db)
    if len(set(args.seeds)) != len(args.seeds):
        raise ValueError("seeds must be unique")
    started = time.perf_counter()
    for path in (args.model_out, args.report_out, args.scores_out):
        path.parent.mkdir(parents=True, exist_ok=True)

    print("[1/6] Building strictly-causal native-currency features", flush=True)
    con = duckdb.connect(str(args.db), read_only=True)
    con.execute("SET TimeZone='UTC'")
    con.execute(f"SET threads={int(args.threads)}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET preserve_insertion_order=false")
    preprocessing, data_report = prepare_feature_tables(
        con,
        window_days=args.window_days,
        degree_cap=args.degree_cap,
    )
    print(json.dumps(data_report["checks"], indent=2), flush=True)

    print("[2/6] Loading train/validation/test matrices", flush=True)
    x_train, y_train, _ = load_split(con, "train")
    x_val, y_val, _ = load_split(con, "val")
    x_test, y_test, test_metadata = load_split(con, "test", include_metadata=True)
    con.close()
    print(
        f"  train={len(y_train):,} val={len(y_val):,} test={len(y_test):,} features={len(FEATURE_COLUMNS)}",
        flush=True,
    )

    print("[3/6] Selecting hyperparameters on validation only", flush=True)
    trials = []
    best: dict[str, Any] | None = None
    primary_seed = args.seeds[0]
    for config in MODEL_GRID:
        trial_started = time.perf_counter()
        model = fit_model(config, x_train, y_train, primary_seed)
        val_score = model.predict_proba(x_val)[:, 1]
        threshold = best_f1_threshold(y_val, val_score)
        result = metrics(y_val, val_score, threshold)
        trials.append(
            {
                "config": config,
                "validation": result,
                "seconds": time.perf_counter() - trial_started,
            }
        )
        print(f"  {config} validation_f1={result['f1']:.6f}", flush=True)
        if best is None or result["f1"] > best["validation"]["f1"]:
            best = {
                "config": config,
                "model": model,
                "threshold": threshold,
                "validation": result,
            }
    if best is None:
        raise RuntimeError("model grid produced no candidate")

    print("[4/6] Running frozen configuration over requested seeds", flush=True)
    seed_results = []
    primary_test_score: np.ndarray | None = None
    for seed in args.seeds:
        model = best["model"] if seed == primary_seed else fit_model(best["config"], x_train, y_train, seed)
        val_score = model.predict_proba(x_val)[:, 1]
        threshold = best_f1_threshold(y_val, val_score)
        test_score = model.predict_proba(x_test)[:, 1]
        result = metrics(y_test, test_score, threshold)
        seed_results.append({"seed": seed, **result})
        print(f"  seed={seed} test_f1={result['f1']:.6f} pr_auc={result['pr_auc']:.6f}", flush=True)
        if seed == primary_seed:
            primary_test_score = test_score
            best["model"] = model
            best["threshold"] = threshold
    if primary_test_score is None or test_metadata is None:
        raise RuntimeError("primary seed did not produce test predictions")

    print("[5/6] Writing portable joblib release and test scores", flush=True)
    bundle = {
        "artifact_format": ARTIFACT_FORMAT,
        "model_version": MODEL_VERSION,
        "model": best["model"],
        "threshold": float(best["threshold"]),
        "feature_columns": list(FEATURE_COLUMNS),
        "categorical_indices": list(CATEGORICAL_INDICES),
        "preprocessing": preprocessing,
        "protocol": {
            "unit": "transaction",
            "causality": "all graph windows end one minute before the scored transaction",
            "window_days": args.window_days,
            "degree_cap": args.degree_cap,
            "degree_cap_fit_scope": "train_only",
            "feature_policy": "no Payment Format; no hour-of-day; native currencies only",
            "fx_policy": "no static FX in ML features; legal/business USD rules stay external",
            "threshold_selection": "max validation minority-class F1",
        },
        "runtime": runtime_metadata(),
        "provenance": {
            "source_database": str(args.db),
            "source_database_sha256": sha256_file(args.db),
            "trained_at": datetime.now(UTC).isoformat(),
            "primary_seed": primary_seed,
            "selected_config": best["config"],
            "split_counts": data_report["split_counts"],
        },
    }
    validate_bundle(bundle)
    joblib.dump(bundle, args.model_out, compress=3)

    scores_sha = None
    if not args.skip_scores:
        scores = test_metadata.copy()
        scores["target_laundering"] = y_test
        scores["score"] = primary_test_score
        scores["threshold"] = float(best["threshold"])
        scores["triggered"] = primary_test_score >= float(best["threshold"])
        scores["model_version"] = MODEL_VERSION
        scores.to_parquet(args.scores_out, index=False)
        scores_sha = sha256_file(args.scores_out)

    f1_values = np.array([row["f1"] for row in seed_results], dtype=float)
    primary_metrics = next(row for row in seed_results if row["seed"] == primary_seed)
    report = {
        "schema_version": "fin07.currency_native_edge.benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "complete" if len(args.seeds) == 5 else "noncanonical_seed_count",
        "model_version": MODEL_VERSION,
        "policy": {
            "uses_original_amount_paid": True,
            "uses_original_payment_currency": True,
            "uses_original_amount_received": True,
            "uses_original_receiving_currency": True,
            "uses_static_fx": False,
            "normalization": "train-only log1p z-score per native currency",
            "payment_format_feature": False,
            "hour_of_day_feature": False,
            "usd_conversion_scope": "external legal/business rules only",
        },
        "features": list(FEATURE_COLUMNS),
        "categorical_features": list(CATEGORICAL_INDICES),
        "data": data_report,
        "selection": {
            "trials": trials,
            "selected_config": best["config"],
            "primary_seed": primary_seed,
            "threshold": float(best["threshold"]),
        },
        "test_primary_seed": primary_metrics,
        "test_over_seeds": {
            "count": len(seed_results),
            "f1_mean": float(f1_values.mean()),
            "f1_sample_std": float(f1_values.std(ddof=1)) if len(f1_values) > 1 else None,
            "runs": seed_results,
        },
        "operating_points": operating_points(y_test, primary_test_score),
        "artifacts": {
            "model": {
                "path": str(args.model_out),
                "sha256": sha256_file(args.model_out),
                "bytes": args.model_out.stat().st_size,
            },
            "test_scores": None
            if args.skip_scores
            else {
                "path": str(args.scores_out),
                "sha256": scores_sha,
                "bytes": args.scores_out.stat().st_size,
            },
        },
        "runtime": {**runtime_metadata(), "seconds": time.perf_counter() - started},
    }
    args.report_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"  model  -> {args.model_out}", flush=True)
    print(f"  report -> {args.report_out}", flush=True)
    if not args.skip_scores:
        print(f"  scores -> {args.scores_out}", flush=True)
    print("[6/6] Complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
