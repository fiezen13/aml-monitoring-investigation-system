"""Current-window account classification baselines for graph artifacts.

The modeling unit is ``(account_key, as_of_ts)``.  The target is positive when
the account participates in a laundering-labelled transaction in the same
half-open 7-day feature window ``[as_of_ts - 7 days, as_of_ts)``.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MODELING_SCHEMA_VERSION = "graph_account_modeling_v1"
TARGET_DEFINITION = (
    "account participates as source or destination in >=1 label_laundering=1 "
    "transaction within [as_of_ts - 7 days, as_of_ts)"
)

ID_COLUMNS = [
    "account_key",
    "as_of_ts",
    "snapshot_date",
    "window",
    "sample_split",
    "feature_schema_version",
    "modeling_schema_version",
]

GRAPH_FEATURE_COLUMNS = [
    "in_degree_7d",
    "out_degree_7d",
    "unique_neighbors_7d",
    "in_out_degree_ratio_7d",
    "new_in_counterparty_ratio_7d",
    "new_out_counterparty_ratio_7d",
    "inflow_concentration_7d",
    "outflow_dispersion_7d",
    "history_available",
    "history_days_observed",
]

DETECTOR_FEATURE_COLUMNS = [
    "fan_in_hit",
    "fan_out_hit",
    "gather_scatter_hit",
    "cycle_hit",
    "cycle_motif_count",
    "cycle_length_min",
    "cycle_length_max",
    "detector_motif_count",
]

TARGET_COLUMN = "target_laundering"


def _sql_path(path: str | Path) -> str:
    return Path(path).resolve().as_posix().replace("'", "''")


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_modeling_table(
    db_path: str | Path,
    graph_features_path: str | Path,
    detections_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Build the account-snapshot modeling table with DuckDB COPY.

    Transaction ``split`` is intentionally ignored for target construction.
    The snapshot's already-frozen ``sample_split`` controls model splitting,
    while the timestamp predicate enforces the current-window target.
    """
    db_path = Path(db_path)
    graph_features_path = Path(graph_features_path)
    detections_path = Path(detections_path)
    output_path = Path(output_path)
    for required in (db_path, graph_features_path, detections_path):
        if not required.exists():
            raise FileNotFoundError(required)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    features_sql = _sql_path(graph_features_path)
    detections_sql = _sql_path(detections_path)
    output_sql = _sql_path(output_path)
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("SET TimeZone='UTC'")
    try:
        con.execute(
            f"""
            COPY (
              WITH detector_agg AS (
                SELECT
                  account_key,
                  as_of_ts,
                  MAX(CASE WHEN detected_pattern = 'FAN_IN' THEN 1 ELSE 0 END)::UTINYINT
                    AS fan_in_hit,
                  MAX(CASE WHEN detected_pattern = 'FAN_OUT' THEN 1 ELSE 0 END)::UTINYINT
                    AS fan_out_hit,
                  MAX(CASE WHEN detected_pattern = 'GATHER_SCATTER' THEN 1 ELSE 0 END)::UTINYINT
                    AS gather_scatter_hit,
                  MAX(CASE WHEN detected_pattern = 'CYCLE' THEN 1 ELSE 0 END)::UTINYINT
                    AS cycle_hit,
                  COUNT(DISTINCT CASE WHEN detected_pattern = 'CYCLE'
                                      THEN pattern_instance_id END)::UINTEGER
                    AS cycle_motif_count,
                  COALESCE(MIN(CASE WHEN detected_pattern = 'CYCLE'
                                    THEN cycle_length END), 0)::UTINYINT
                    AS cycle_length_min,
                  COALESCE(MAX(CASE WHEN detected_pattern = 'CYCLE'
                                    THEN cycle_length END), 0)::UTINYINT
                    AS cycle_length_max,
                  COUNT(DISTINCT pattern_instance_id)::UINTEGER AS detector_motif_count
                FROM read_parquet('{detections_sql}')
                GROUP BY account_key, as_of_ts
              ),
              laundering_account_events AS (
                SELECT occurred_at, from_account_key AS account_key
                FROM transaction
                WHERE label_laundering = 1
                UNION ALL
                SELECT occurred_at, to_account_key AS account_key
                FROM transaction
                WHERE label_laundering = 1
              ),
              positive_keys AS (
                SELECT DISTINCT f.account_key, f.as_of_ts
                FROM read_parquet('{features_sql}') f
                INNER JOIN laundering_account_events e
                  ON e.account_key = f.account_key
                 AND e.occurred_at >= f.as_of_ts - INTERVAL 7 DAY
                 AND e.occurred_at < f.as_of_ts
              )
              SELECT
                f.account_key,
                f.as_of_ts,
                f.snapshot_date,
                f.window,
                f.sample_split,
                f.feature_schema_version,
                '{MODELING_SCHEMA_VERSION}'::VARCHAR AS modeling_schema_version,
                f.in_degree_7d,
                f.out_degree_7d,
                f.unique_neighbors_7d,
                f.in_out_degree_ratio_7d,
                f.new_in_counterparty_ratio_7d,
                f.new_out_counterparty_ratio_7d,
                f.inflow_concentration_7d,
                f.outflow_dispersion_7d,
                f.history_available,
                f.history_days_observed,
                COALESCE(d.fan_in_hit, 0)::UTINYINT AS fan_in_hit,
                COALESCE(d.fan_out_hit, 0)::UTINYINT AS fan_out_hit,
                COALESCE(d.gather_scatter_hit, 0)::UTINYINT AS gather_scatter_hit,
                COALESCE(d.cycle_hit, 0)::UTINYINT AS cycle_hit,
                COALESCE(d.cycle_motif_count, 0)::UINTEGER AS cycle_motif_count,
                COALESCE(d.cycle_length_min, 0)::UTINYINT AS cycle_length_min,
                COALESCE(d.cycle_length_max, 0)::UTINYINT AS cycle_length_max,
                COALESCE(d.detector_motif_count, 0)::UINTEGER AS detector_motif_count,
                (p.account_key IS NOT NULL)::UTINYINT AS target_laundering
              FROM read_parquet('{features_sql}') f
              LEFT JOIN detector_agg d USING (account_key, as_of_ts)
              LEFT JOIN positive_keys p USING (account_key, as_of_ts)
              ORDER BY f.as_of_ts, f.account_key
            ) TO '{output_sql}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
            """
        )
    finally:
        con.close()

    con = duckdb.connect()
    try:
        rows = con.execute(
            f"""
            SELECT sample_split,
                   COUNT(*) AS rows,
                   SUM(target_laundering)::BIGINT AS positives,
                   COUNT(*) - SUM(target_laundering)::BIGINT AS negatives,
                   COUNT(DISTINCT as_of_ts) AS snapshots
            FROM read_parquet('{output_sql}')
            GROUP BY sample_split ORDER BY sample_split
            """
        ).fetchall()
        duplicate_keys = con.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT account_key, as_of_ts
              FROM read_parquet('{output_sql}')
              GROUP BY 1, 2 HAVING COUNT(*) != 1
            )
            """
        ).fetchone()[0]
        invalid = con.execute(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE "window" != '7d'),
              COUNT(*) FILTER (WHERE sample_split NOT IN ('train','val','test')),
              COUNT(*) FILTER (WHERE target_laundering NOT IN (0,1))
            FROM read_parquet('{output_sql}')
            """
        ).fetchone()
    finally:
        con.close()
    if duplicate_keys or any(invalid):
        raise ValueError(f"invalid modeling artifact: duplicate_keys={duplicate_keys}, checks={invalid}")

    counts = {
        split: {
            "rows": int(n),
            "positives": int(pos),
            "negatives": int(neg),
            "snapshots": int(snapshots),
            "positive_rate": float(pos / n),
        }
        for split, n, pos, neg, snapshots in rows
    }
    return {
        "modeling_schema_version": MODELING_SCHEMA_VERSION,
        "target_definition": TARGET_DEFINITION,
        "window_semantics": "start-inclusive/end-exclusive",
        "row_counts": counts,
        "total_rows": sum(item["rows"] for item in counts.values()),
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
    }


def load_split(
    modeling_path: str | Path,
    split: str,
    feature_columns: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    if split not in {"train", "val", "test"}:
        raise ValueError(f"unknown split: {split}")
    unknown = set(feature_columns) - set(GRAPH_FEATURE_COLUMNS + DETECTOR_FEATURE_COLUMNS)
    if unknown:
        raise ValueError(f"non-feature columns requested: {sorted(unknown)}")
    path_sql = _sql_path(modeling_path)
    select_columns = ", ".join([*feature_columns, TARGET_COLUMN])
    con = duckdb.connect()
    try:
        frame = con.execute(
            f"""
            SELECT {select_columns}
            FROM read_parquet('{path_sql}')
            WHERE sample_split = ?
            ORDER BY as_of_ts, account_key
            """,
            [split],
        ).fetchdf()
    finally:
        con.close()
    y = frame.pop(TARGET_COLUMN).to_numpy(dtype=np.uint8, copy=False)
    x = frame.to_numpy(dtype=np.float32, copy=False)
    if not np.isfinite(x).all():
        raise ValueError(f"non-finite feature value in split={split}")
    return x, y


def make_models(random_state: int = 42) -> dict[str, Any]:
    """Fixed, deliberately small baseline set; no hyperparameter search."""
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=1.0,
                class_weight="balanced",
                solver="lbfgs",
                max_iter=200,
                random_state=random_state,
            ),
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.1,
            max_iter=100,
            max_leaf_nodes=31,
            min_samples_leaf=100,
            l2_regularization=1.0,
            class_weight="balanced",
            early_stopping=False,
            random_state=random_state,
        ),
    }


def positive_scores(model: Any, x: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict_proba(x)[:, 1], dtype=np.float64)


def select_threshold_on_validation(
    y_true: np.ndarray,
    scores: np.ndarray,
    max_alert_rate: float = 0.01,
) -> dict[str, float | int]:
    """Maximize validation F1 subject to a maximum alert rate.

    Candidate cutoffs are complete equal-score groups, so the reported scalar
    threshold reproduces the selected validation alert set exactly.
    """
    if len(y_true) == 0 or not 0 < max_alert_rate <= 1:
        raise ValueError("non-empty labels and 0 < max_alert_rate <= 1 required")
    order = np.argsort(-scores, kind="stable")
    sorted_scores = scores[order]
    sorted_y = y_true[order].astype(np.int64, copy=False)
    cumulative_tp = np.cumsum(sorted_y)
    group_ends = np.flatnonzero(np.r_[sorted_scores[:-1] != sorted_scores[1:], True])
    budget = max(1, math.floor(len(y_true) * max_alert_rate))
    eligible = group_ends[group_ends < budget]
    if eligible.size == 0:
        return {
            "threshold": float(np.nextafter(sorted_scores[0], np.inf)),
            "f1": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "alerts": 0,
            "alert_rate": 0.0,
        }
    alerts = eligible + 1
    tp = cumulative_tp[eligible]
    positives = int(y_true.sum())
    precision = tp / alerts
    recall = tp / positives if positives else np.zeros_like(tp, dtype=float)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision, dtype=float),
        where=(precision + recall) > 0,
    )
    best = int(np.argmax(f1))
    end = int(eligible[best])
    return {
        "threshold": float(sorted_scores[end]),
        "f1": float(f1[best]),
        "precision": float(precision[best]),
        "recall": float(recall[best]),
        "alerts": int(alerts[best]),
        "alert_rate": float(alerts[best] / len(y_true)),
    }


def evaluate_scores(
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    precision_k: int = 1000,
    alert_budget_rate: float = 0.01,
) -> dict[str, float | int]:
    n = len(y_true)
    positives = int(y_true.sum())
    k = min(precision_k, n)
    budget = min(max(1, math.floor(n * alert_budget_rate)), n)
    max_rank = max(k, budget)
    top = np.argpartition(-scores, max_rank - 1)[:max_rank]
    top = top[np.argsort(-scores[top], kind="stable")]
    precision_at_k = float(y_true[top[:k]].sum() / k)
    recall_at_budget = float(y_true[top[:budget]].sum() / positives) if positives else 0.0

    predicted = scores >= threshold
    alerts = int(predicted.sum())
    tp = int(y_true[predicted].sum())
    precision = float(tp / alerts) if alerts else 0.0
    recall = float(tp / positives) if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "rows": n,
        "positives": positives,
        "pr_auc": float(average_precision_score(y_true, scores)),
        "precision_at_k": precision_at_k,
        "precision_k": k,
        "recall_at_fixed_alert_budget": recall_at_budget,
        "fixed_alert_budget": budget,
        "fixed_alert_budget_rate": float(budget / n),
        "threshold": float(threshold),
        "threshold_precision": precision,
        "threshold_recall": recall,
        "f1": float(f1),
        "alerts": alerts,
        "alert_rate": float(alerts / n),
    }


def run_baselines(
    modeling_path: str | Path,
    precision_k: int = 1000,
    alert_budget_rate: float = 0.01,
    random_state: int = 42,
) -> dict[str, Any]:
    """Fit on train, select thresholds on val, then score test once."""
    feature_sets = {
        "graph_features_only": GRAPH_FEATURE_COLUMNS,
        "graph_plus_detector_features": GRAPH_FEATURE_COLUMNS + DETECTOR_FEATURE_COLUMNS,
    }
    trained: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}

    for feature_set_name, columns in feature_sets.items():
        x_train, y_train = load_split(modeling_path, "train", columns)
        x_val, y_val = load_split(modeling_path, "val", columns)
        trained[feature_set_name] = {}
        results[feature_set_name] = {}
        for model_name, model in make_models(random_state).items():
            started = time.perf_counter()
            model.fit(x_train, y_train)
            fit_seconds = time.perf_counter() - started
            val_scores = positive_scores(model, x_val)
            selected = select_threshold_on_validation(y_val, val_scores, max_alert_rate=alert_budget_rate)
            val_metrics = evaluate_scores(
                y_val,
                val_scores,
                threshold=float(selected["threshold"]),
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )
            trained[feature_set_name][model_name] = model
            results[feature_set_name][model_name] = {
                "feature_count": len(columns),
                "fit_seconds": fit_seconds,
                "validation_threshold_selection": selected,
                "validation_metrics": val_metrics,
            }
        del x_train, y_train, x_val, y_val

    selected_by_feature_set = {
        feature_set: max(
            model_results,
            key=lambda name: model_results[name]["validation_metrics"]["pr_auc"],
        )
        for feature_set, model_results in results.items()
    }

    # This is the only test-data pass. All models, feature sets and thresholds
    # are already frozen from train/validation above.
    for feature_set_name, columns in feature_sets.items():
        x_test, y_test = load_split(modeling_path, "test", columns)
        for model_name, model in trained[feature_set_name].items():
            scores = positive_scores(model, x_test)
            threshold = results[feature_set_name][model_name]["validation_threshold_selection"]["threshold"]
            results[feature_set_name][model_name]["test_metrics"] = evaluate_scores(
                y_test,
                scores,
                threshold=float(threshold),
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )
        del x_test, y_test

    return {
        "protocol": {
            "task": "current-window account classification",
            "target_definition": TARGET_DEFINITION,
            "split_policy": "fit=train; model/threshold selection=val; test=one final pass",
            "threshold_policy": ("maximize validation F1 subject to alert_rate <= fixed alert budget"),
            "precision_k": precision_k,
            "fixed_alert_budget_rate": alert_budget_rate,
            "hyperparameter_search": False,
            "random_state": random_state,
        },
        "feature_sets": feature_sets,
        "model_parameters": {
            "logistic_regression": {
                "scaler": "StandardScaler",
                "C": 1.0,
                "class_weight": "balanced",
                "solver": "lbfgs",
                "max_iter": 200,
            },
            "hist_gradient_boosting": {
                "learning_rate": 0.1,
                "max_iter": 100,
                "max_leaf_nodes": 31,
                "min_samples_leaf": 100,
                "l2_regularization": 1.0,
                "class_weight": "balanced",
                "early_stopping": False,
            },
        },
        "selected_model_by_feature_set": selected_by_feature_set,
        "results": results,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "duckdb": duckdb.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
