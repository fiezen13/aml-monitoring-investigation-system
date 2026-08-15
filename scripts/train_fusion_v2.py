#!/usr/bin/env python3
"""Retrain IF + Graph on one mature 7-day protocol and build fusion v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_isolation_forest import FEATURE_COLS  # noqa: E402
from src.fusion.model import (  # noqa: E402
    PercentileCalibration,
    build_fusion_bundle,
    fit_percentile_calibration,
    isolation_forest_scores,
    save_fusion_bundle,
)
from src.fusion.training import (  # noqa: E402
    TemporalSplit,
    choose_champion,
    parse_temporal_splits,
    select_fusion_weights,
)
from src.models.graph_baseline import (  # noqa: E402
    DETECTOR_FEATURE_COLUMNS,
    GRAPH_FEATURE_COLUMNS,
    evaluate_scores,
    make_models,
    positive_scores,
    select_threshold_on_validation,
)

DEFAULT_CONFIG = ROOT / "configs/fusion/if_graph_v2.json"
DEFAULT_IF_MODEL = ROOT / "models/fin07_if_7d_v2.joblib"
DEFAULT_GRAPH_MODEL = ROOT / "models/fin07_graph_7d_v2.joblib"
DEFAULT_BUNDLE = ROOT / "models/fin07_if_graph_fusion_v2.joblib"
DEFAULT_SCORES = ROOT / "data/processed/fusion-v2/fusion_scores.parquet"
DEFAULT_REPORT = ROOT / "reports/fusion-v2/benchmark.json"
DEFAULT_MANIFEST = ROOT / "reports/fusion-v2/manifest.json"

GRAPH_COLUMNS = GRAPH_FEATURE_COLUMNS + DETECTOR_FEATURE_COLUMNS
EXPLANATION_COLUMNS = [
    "fan_in_hit",
    "fan_out_hit",
    "gather_scatter_hit",
    "cycle_hit",
    "detector_motif_count",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--if-model-out", type=Path, default=DEFAULT_IF_MODEL)
    parser.add_argument("--graph-model-out", type=Path, default=DEFAULT_GRAPH_MODEL)
    parser.add_argument("--bundle-out", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--scores-out", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _sql_path(path: str | Path) -> str:
    return _resolve(path).as_posix().replace("'", "''")


def sha256_file(path: str | Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def load_config(path: Path) -> tuple[dict[str, Any], dict[str, TemporalSplit]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "fin07.fusion.training.v2":
        raise ValueError("unsupported fusion-v2 training config")
    if config.get("window") != "7d":
        raise ValueError("fusion-v2 requires window=7d")
    splits = parse_temporal_splits(config["snapshot_splits"])
    if splits["train"].start < datetime(2022, 9, 8, tzinfo=UTC):
        raise ValueError("train includes an immature 7-day snapshot")
    return config, splits


def _open_training_database(config: dict[str, Any]) -> duckdb.DuckDBPyConnection:
    if_glob = _sql_path(config["inputs"]["isolation_forest_features_glob"])
    graph_path = _resolve(config["inputs"]["graph_modeling"])
    if not graph_path.is_file():
        raise FileNotFoundError(graph_path)
    if not list(ROOT.glob(str(config["inputs"]["isolation_forest_features_glob"]).replace(str(ROOT) + "/", ""))):
        raise FileNotFoundError(config["inputs"]["isolation_forest_features_glob"])

    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET threads=4")
    connection.execute(
        f"""
        CREATE VIEW if_features AS
        SELECT *, as_of_ts + INTERVAL 1 SECOND AS canonical_as_of_ts
        FROM read_parquet('{if_glob}')
        """
    )
    connection.execute(f"CREATE VIEW graph_modeling AS SELECT * FROM read_parquet('{_sql_path(graph_path)}')")
    duplicates = connection.execute(
        """
        SELECT count(*) FROM (
          SELECT account_key, canonical_as_of_ts, count(*) AS n
          FROM if_features GROUP BY 1, 2 HAVING n != 1
        )
        """
    ).fetchone()[0]
    if duplicates:
        connection.close()
        raise ValueError(f"IF feature keys are not unique after timestamp alignment: {duplicates}")
    return connection


def _validate_alignment(
    connection: duckdb.DuckDBPyConnection,
    splits: dict[str, TemporalSplit],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for name, split in splits.items():
        graph_rows, matched, positives = connection.execute(
            """
            SELECT count(*), count(i.account_key), sum(g.target_laundering)
            FROM graph_modeling g
            LEFT JOIN if_features i
              ON i.account_key = g.account_key
             AND i.canonical_as_of_ts = g.as_of_ts
            WHERE g.as_of_ts >= ? AND g.as_of_ts < ?
            """,
            [split.start, split.end],
        ).fetchone()
        if graph_rows == 0 or graph_rows != matched:
            raise ValueError(f"unaligned split={name}: graph={graph_rows}, matched_if={matched}")
        result[name] = {"rows": int(graph_rows), "positives": int(positives)}
    return result


def _load_split_frame(
    connection: duckdb.DuckDBPyConnection,
    split: TemporalSplit,
) -> pd.DataFrame:
    if_select = ", ".join(f'i."{column}" AS "if__{column}"' for column in FEATURE_COLS)
    graph_select = ", ".join(f'g."{column}" AS "graph__{column}"' for column in GRAPH_COLUMNS)
    return connection.execute(
        f"""
        SELECT
          g.account_key,
          g.as_of_ts,
          g.target_laundering,
          {if_select},
          {graph_select}
        FROM graph_modeling g
        INNER JOIN if_features i
          ON i.account_key = g.account_key
         AND i.canonical_as_of_ts = g.as_of_ts
        WHERE g.as_of_ts >= ? AND g.as_of_ts < ?
        ORDER BY g.as_of_ts, g.account_key
        """,
        [split.start, split.end],
    ).fetchdf()


def _matrices(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if_matrix = frame[[f"if__{column}" for column in FEATURE_COLS]].to_numpy(dtype=np.float64, copy=False)
    graph_matrix = frame[[f"graph__{column}" for column in GRAPH_COLUMNS]].to_numpy(dtype=np.float32, copy=False)
    labels = frame["target_laundering"].to_numpy(dtype=np.uint8, copy=False)
    if not np.isfinite(if_matrix).all() or not np.isfinite(graph_matrix).all():
        raise ValueError("training features contain non-finite values")
    return if_matrix, graph_matrix, labels


def _raw_scores_frame(
    frame: pd.DataFrame,
    *,
    split: str,
    if_scores: np.ndarray,
    graph_scores: np.ndarray,
) -> pd.DataFrame:
    result = frame[["account_key", "as_of_ts", "target_laundering"]].copy()
    result["sample_split"] = split
    for column in EXPLANATION_COLUMNS:
        result[column] = frame[f"graph__{column}"].to_numpy(copy=False)
    result["isolation_forest_raw_score"] = if_scores
    result["graph_raw_score"] = graph_scores
    return result


def _fit_if_artifact(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    if_matrix, _, _ = _matrices(frame)
    declaration = config["isolation_forest"]
    model = IsolationForest(
        n_estimators=int(declaration["n_estimators"]),
        contamination=float(declaration["contamination"]),
        random_state=int(declaration["random_state"]),
        n_jobs=-1,
    )
    model.fit(if_matrix)
    raw = -np.asarray(model.decision_function(if_matrix), dtype=np.float64)
    scaler = MinMaxScaler(feature_range=(0.0, 1.0)).fit(raw.reshape(-1, 1))
    return {
        "model": model,
        "scaler": scaler,
        "feature_cols": list(FEATURE_COLS),
        "window": "7d",
        "score_range": (0.0, 1.0),
        "score_meaning": "1.0 = highest review priority",
        "model_version": declaration["model_version"],
    }


def _score_frame(
    frame: pd.DataFrame,
    if_artifact: dict[str, Any],
    graph_model: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if_matrix, graph_matrix, labels = _matrices(frame)
    return (
        isolation_forest_scores(if_artifact, if_matrix),
        positive_scores(graph_model, graph_matrix),
        labels,
    )


def _component_metrics(
    labels: np.ndarray,
    scores: dict[str, np.ndarray],
    thresholds: dict[str, float],
    *,
    precision_k: int,
    alert_budget_rate: float,
) -> dict[str, dict[str, float | int]]:
    return {
        name: evaluate_scores(
            labels,
            values,
            thresholds[name],
            precision_k=precision_k,
            alert_budget_rate=alert_budget_rate,
        )
        for name, values in scores.items()
    }


def _finalize_scores(
    raw_path: Path,
    output_path: Path,
    *,
    if_calibration: PercentileCalibration,
    graph_calibration: PercentileCalibration,
    weights: dict[str, float],
    champion: str,
    champion_threshold: float,
    fusion_threshold: float,
    config: dict[str, Any],
) -> None:
    frame = pd.read_parquet(raw_path)
    if_percentile = if_calibration.transform(frame["isolation_forest_raw_score"].to_numpy(dtype=np.float64))
    graph_percentile = graph_calibration.transform(frame["graph_raw_score"].to_numpy(dtype=np.float64))
    if_contribution = float(weights["isolation_forest"]) * if_percentile
    graph_contribution = float(weights["graph"]) * graph_percentile
    fusion_score = np.clip(if_contribution + graph_contribution, 0.0, 1.0)
    champion_score = graph_percentile if champion == "graph" else fusion_score

    frame["isolation_forest_percentile"] = if_percentile
    frame["graph_percentile"] = graph_percentile
    frame["isolation_forest_contribution"] = if_contribution
    frame["graph_contribution"] = graph_contribution
    frame["fusion_score"] = fusion_score
    frame["fusion_complete"] = True
    frame["champion"] = champion
    frame["champion_score"] = champion_score
    frame["champion_threshold"] = champion_threshold
    frame["fusion_threshold"] = fusion_threshold
    frame["triggered"] = champion_score >= champion_threshold
    frame["window"] = "7d"
    frame["if_model_version"] = config["isolation_forest"]["model_version"]
    frame["graph_model_version"] = config["graph"]["model_version"]
    frame["fusion_version"] = config["fusion_version"]
    frame.to_parquet(output_path, index=False)


def train_release(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    config_path = args.config.resolve()
    config, splits = load_config(config_path)
    precision_k = int(config["validation"]["precision_k"])
    alert_budget_rate = float(config["validation"]["alert_budget_rate"])
    quantile_count = int(config["calibration"]["quantile_count"])

    output_paths = {
        "if_model": args.if_model_out.resolve(),
        "graph_model": args.graph_model_out.resolve(),
        "bundle": args.bundle_out.resolve(),
        "scores": args.scores_out.resolve(),
        "report": args.report_out.resolve(),
        "manifest": args.manifest_out.resolve(),
    }
    for path in output_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = _open_training_database(config)
    try:
        split_counts = _validate_alignment(connection, splits)
        with tempfile.TemporaryDirectory(prefix="fin07-fusion-v2-") as temp_name:
            temp_dir = Path(temp_name)
            raw_paths: dict[str, Path] = {}

            print("[1/6] Loading mature train snapshots and fitting IF + Graph", flush=True)
            train_frame = _load_split_frame(connection, splits["train"])
            if_artifact = _fit_if_artifact(train_frame, config)
            graph_model = make_models(int(config["graph"]["random_state"]))["hist_gradient_boosting"]
            _, graph_train, train_labels = _matrices(train_frame)
            graph_model.fit(graph_train, train_labels)
            train_if_scores, train_graph_scores, _ = _score_frame(train_frame, if_artifact, graph_model)
            if_calibration = fit_percentile_calibration(train_if_scores, quantile_count=quantile_count)
            graph_calibration = fit_percentile_calibration(train_graph_scores, quantile_count=quantile_count)
            raw_paths["train"] = temp_dir / "raw_train.parquet"
            _raw_scores_frame(
                train_frame,
                split="train",
                if_scores=train_if_scores,
                graph_scores=train_graph_scores,
            ).to_parquet(raw_paths["train"], index=False)
            del train_frame, graph_train

            print("[2/6] Selecting weights, thresholds and champion on validation", flush=True)
            val_frame = _load_split_frame(connection, splits["val"])
            val_if_scores, val_graph_scores, val_labels = _score_frame(val_frame, if_artifact, graph_model)
            val_if_percentile = if_calibration.transform(val_if_scores)
            val_graph_percentile = graph_calibration.transform(val_graph_scores)
            weights, weight_selection = select_fusion_weights(
                if_percentile=val_if_percentile,
                graph_percentile=val_graph_percentile,
                labels=val_labels,
                minimum_component_weight=float(config["weight_selection"]["minimum_component_weight"]),
                step=float(config["weight_selection"]["step"]),
                alert_budget_rate=alert_budget_rate,
            )
            val_fusion = weights["isolation_forest"] * val_if_percentile + weights["graph"] * val_graph_percentile
            selections = {
                "isolation_forest": select_threshold_on_validation(
                    val_labels, val_if_percentile, max_alert_rate=alert_budget_rate
                ),
                "graph": select_threshold_on_validation(
                    val_labels, val_graph_percentile, max_alert_rate=alert_budget_rate
                ),
                "fusion": weight_selection["selected"],
            }
            thresholds = {name: float(selection["threshold"]) for name, selection in selections.items()}
            validation_metrics = _component_metrics(
                val_labels,
                {
                    "isolation_forest": val_if_percentile,
                    "graph": val_graph_percentile,
                    "fusion": val_fusion,
                },
                thresholds,
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )
            champion = choose_champion({name: validation_metrics[name] for name in ("graph", "fusion")})
            champion_threshold = thresholds[champion]
            raw_paths["val"] = temp_dir / "raw_val.parquet"
            _raw_scores_frame(
                val_frame,
                split="val",
                if_scores=val_if_scores,
                graph_scores=val_graph_scores,
            ).to_parquet(raw_paths["val"], index=False)
            del val_frame, val_if_percentile, val_graph_percentile, val_fusion

            print(f"[3/6] Frozen champion={champion}; running the final test pass", flush=True)
            test_frame = _load_split_frame(connection, splits["test"])
            test_if_scores, test_graph_scores, test_labels = _score_frame(test_frame, if_artifact, graph_model)
            test_if_percentile = if_calibration.transform(test_if_scores)
            test_graph_percentile = graph_calibration.transform(test_graph_scores)
            test_fusion = weights["isolation_forest"] * test_if_percentile + weights["graph"] * test_graph_percentile
            test_metrics = _component_metrics(
                test_labels,
                {
                    "isolation_forest": test_if_percentile,
                    "graph": test_graph_percentile,
                    "fusion": test_fusion,
                },
                thresholds,
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )
            raw_paths["test"] = temp_dir / "raw_test.parquet"
            _raw_scores_frame(
                test_frame,
                split="test",
                if_scores=test_if_scores,
                graph_scores=test_graph_scores,
            ).to_parquet(raw_paths["test"], index=False)
            del test_frame, test_if_percentile, test_graph_percentile, test_fusion

            print("[4/6] Writing models, bundle and canonical scores", flush=True)
            joblib.dump(if_artifact, output_paths["if_model"], compress=3)
            joblib.dump(graph_model, output_paths["graph_model"], compress=3)
            provenance = {
                "training_config": _relative(config_path),
                "training_config_sha256": sha256_file(config_path),
                "graph_modeling": config["inputs"]["graph_modeling"],
                "graph_modeling_sha256": sha256_file(_resolve(config["inputs"]["graph_modeling"])),
                "snapshot_splits": config["snapshot_splits"],
                "warmup_policy": config["warmup_policy"],
                "champion": champion,
            }
            bundle = build_fusion_bundle(
                fusion_version=config["fusion_version"],
                isolation_forest_artifact=if_artifact,
                graph_model=graph_model,
                graph_feature_cols=GRAPH_COLUMNS,
                graph_model_version=config["graph"]["model_version"],
                if_calibration=if_calibration,
                graph_calibration=graph_calibration,
                weights=weights,
                threshold=thresholds["fusion"],
                provenance=provenance,
            )
            bundle["champion"] = champion
            bundle["champion_threshold"] = champion_threshold
            bundle["component_thresholds"] = thresholds
            save_fusion_bundle(bundle, output_paths["bundle"])

            scored_paths: list[Path] = []
            for name in ("train", "val", "test"):
                scored = temp_dir / f"scored_{name}.parquet"
                _finalize_scores(
                    raw_paths[name],
                    scored,
                    if_calibration=if_calibration,
                    graph_calibration=graph_calibration,
                    weights=weights,
                    champion=champion,
                    champion_threshold=champion_threshold,
                    fusion_threshold=thresholds["fusion"],
                    config=config,
                )
                scored_paths.append(scored)
            union = ", ".join(f"'{_sql_path(path)}'" for path in scored_paths)
            destination = _sql_path(output_paths["scores"])
            connection.execute(
                f"""
                COPY (
                  SELECT * FROM read_parquet([{union}])
                  ORDER BY as_of_ts, account_key
                ) TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
                """
            )
    finally:
        connection.close()

    print("[5/6] Writing benchmark and provenance manifest", flush=True)
    benchmark = {
        "schema_version": "fin07.fusion.benchmark.v2",
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": {
            "window": "7d",
            "window_semantics": config["canonical_window_semantics"],
            "fit": "train only",
            "calibration_weight_threshold_selection": "validation only",
            "test": "one final pass after champion freeze",
            "alert_budget_rate": alert_budget_rate,
            "precision_k": precision_k,
            "warmup_policy": config["warmup_policy"],
        },
        "snapshot_splits": config["snapshot_splits"],
        "split_counts": split_counts,
        "selection": {
            "weights": weights,
            "weight_search": weight_selection,
            "thresholds": thresholds,
            "champion": champion,
            "champion_threshold": champion_threshold,
            "basis": "validation_f1_within_alert_budget_then_pr_auc",
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "duckdb": duckdb.__version__,
            "scikit_learn": sklearn.__version__,
            "seconds": round(time.perf_counter() - started, 3),
        },
    }
    output_paths["report"].write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    score_connection = duckdb.connect()
    try:
        score_counts = {
            split: int(count)
            for split, count in score_connection.execute(
                f"SELECT sample_split, count(*) FROM read_parquet('{_sql_path(output_paths['scores'])}') GROUP BY 1"
            ).fetchall()
        }
        latest_snapshot, latest_rows, latest_alerts = score_connection.execute(
            f"""
            SELECT max(as_of_ts),
                   count(*) FILTER (WHERE as_of_ts = (SELECT max(as_of_ts) FROM read_parquet('{_sql_path(output_paths["scores"])}'))),
                   count(*) FILTER (WHERE as_of_ts = (SELECT max(as_of_ts) FROM read_parquet('{_sql_path(output_paths["scores"])}')) AND triggered)
            FROM read_parquet('{_sql_path(output_paths["scores"])}')
            """
        ).fetchone()
    finally:
        score_connection.close()

    manifest = {
        "schema_version": "fin07.fusion.release.v2",
        "created_at": datetime.now(UTC).isoformat(),
        "fusion_version": config["fusion_version"],
        "champion": champion,
        "champion_threshold": champion_threshold,
        "input_artifacts": {
            "duckdb": {
                "path": config["inputs"]["duckdb"],
                "sha256": sha256_file(_resolve(config["inputs"]["duckdb"])),
            },
            "graph_modeling": {
                "path": config["inputs"]["graph_modeling"],
                "sha256": sha256_file(_resolve(config["inputs"]["graph_modeling"])),
            },
            "isolation_forest_features": [
                {"path": _relative(path), "sha256": sha256_file(path)}
                for path in sorted((ROOT / "data/processed/behavior-7d").glob("features_*_7d.parquet"))
            ],
        },
        "artifacts": {
            name: {"path": _relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for name, path in output_paths.items()
            if name != "manifest"
        },
        "score_rows": score_counts,
        "deployment_snapshot": {
            "as_of_ts": latest_snapshot.isoformat(),
            "rows": int(latest_rows),
            "triggered": int(latest_alerts),
        },
        "benchmark_summary": {
            "validation": validation_metrics[champion],
            "test": test_metrics[champion],
        },
    }
    output_paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[6/6] Complete", flush=True)
    print(json.dumps({"champion": champion, "manifest": _relative(output_paths["manifest"])}, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> int:
    train_release(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
