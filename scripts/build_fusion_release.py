#!/usr/bin/env python3
"""Build the canonical FIN-07 Isolation Forest + Graph fusion release.

This command validates both handoff packages by SHA-256, repairs their known
contract differences, calibrates both scores from train only, selects one
validation threshold, writes the fused account-snapshot score table and packs
the two estimators into one versioned runtime bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fusion.model import (  # noqa: E402
    build_fusion_bundle,
    fit_percentile_calibration,
    isolation_forest_scores,
    load_graph_model_compat,
    save_fusion_bundle,
)
from src.models.graph_baseline import (  # noqa: E402
    DETECTOR_FEATURE_COLUMNS,
    GRAPH_FEATURE_COLUMNS,
    evaluate_scores,
    select_threshold_on_validation,
)

DEFAULT_CONFIG = ROOT / "configs/fusion/if_graph_v1.json"
DEFAULT_BUNDLE = ROOT / "models/fin07_if_graph_fusion_v1.joblib"
DEFAULT_SCORES = ROOT / "data/processed/fusion_scores_v1.parquet"
DEFAULT_REPORT = ROOT / "reports/fusion_release_v1.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bundle-out", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--scores-out", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-checksums", action="store_true", help="Local development only")
    return parser.parse_args(argv)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _sql_path(path: str | Path) -> str:
    return _resolve(path).as_posix().replace("'", "''")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "fin07.fusion.config.v1":
        raise ValueError("unsupported fusion config schema")
    if config.get("window") != "7d":
        raise ValueError("the frozen fusion release requires window=7d")
    if config.get("missing_component_policy") != "renormalize_available_weights":
        raise ValueError("unsupported missing component policy")
    offset = config.get("timestamp_alignment", {}).get("isolation_forest_offset_seconds")
    if offset != 1:
        raise ValueError("the handed IF timestamps require the reviewed +1 second alignment")
    return config


def validate_artifacts(config: dict[str, Any], *, checksums: bool) -> dict[str, dict[str, Any]]:
    validated: dict[str, dict[str, Any]] = {}
    for name, declaration in config["artifacts"].items():
        path = _resolve(declaration["path"])
        if not path.is_file():
            raise FileNotFoundError(f"missing {name}: {path}")
        actual = sha256_file(path) if checksums else None
        expected = declaration["sha256"]
        if checksums and actual != expected:
            raise ValueError(f"checksum mismatch for {name}: expected={expected} actual={actual}")
        validated[name] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": actual or expected,
            "bytes": path.stat().st_size,
        }
    return validated


def _load_if_artifact(path: Path) -> dict[str, Any]:
    artifact = joblib.load(path)
    if not isinstance(artifact, dict):
        raise ValueError("Isolation Forest handoff model must be a dictionary")
    required = {"model", "scaler", "feature_cols", "window"}
    missing = required - set(artifact)
    if missing:
        raise ValueError(f"Isolation Forest artifact missing keys: {sorted(missing)}")
    if len(artifact["feature_cols"]) != 20 or artifact["window"] != "7d":
        raise ValueError("Isolation Forest model must use 20 features and window=7d")
    artifact = dict(artifact)
    artifact["model_version"] = str(artifact.get("model_version") or "if_behavior_7d_huong_v1")
    return artifact


def _feature_match(alias_a: str, alias_b: str, columns: list[str]) -> str:
    return " AND ".join(f'{alias_a}."{column}" IS NOT DISTINCT FROM {alias_b}."{column}"' for column in columns)


def canonical_if_sql(config: dict[str, Any], feature_cols: list[str]) -> str:
    artifacts = config["artifacts"]
    scores = _sql_path(artifacts["isolation_forest_scores"]["path"])
    train = _sql_path(artifacts["isolation_forest_train_features"]["path"])
    val = _sql_path(artifacts["isolation_forest_val_features"]["path"])
    test = _sql_path(artifacts["isolation_forest_test_features"]["path"])
    graph = _sql_path(artifacts["graph_scores"]["path"])
    match = _feature_match("i", "f", feature_cols)
    return f"""
        WITH source_features AS (
            SELECT 'train'::VARCHAR AS source_split, *
            FROM read_parquet('{train}')
            UNION ALL BY NAME
            SELECT 'val'::VARCHAR AS source_split, *
            FROM read_parquet('{val}')
            UNION ALL BY NAME
            SELECT 'test'::VARCHAR AS source_split, *
            FROM read_parquet('{test}')
        ),
        mapped AS (
            SELECT
                i.account_key,
                i.as_of_ts + INTERVAL 1 SECOND AS as_of_ts,
                i.anomaly_score,
                COALESCE(NULLIF(i.model_version, ''), 'if_behavior_7d_huong_v1')
                    AS if_model_version,
                f.source_split
            FROM read_parquet('{scores}') i
            INNER JOIN source_features f
                ON i.account_key = f.account_key
               AND i.as_of_ts = f.as_of_ts
               AND {match}
        ),
        candidates AS (
            SELECT
                m.account_key,
                m.as_of_ts,
                g.sample_split,
                m.anomaly_score,
                m.if_model_version,
                ROW_NUMBER() OVER (
                    PARTITION BY m.account_key, m.as_of_ts
                    ORDER BY
                        CASE WHEN m.source_split = g.sample_split THEN 0 ELSE 1 END,
                        CASE m.source_split WHEN 'test' THEN 0 WHEN 'val' THEN 1 ELSE 2 END,
                        m.anomaly_score DESC
                ) AS choice_rank
            FROM mapped m
            INNER JOIN read_parquet('{graph}') g
                ON m.account_key = g.account_key
               AND m.as_of_ts = g.as_of_ts
        )
        SELECT account_key, as_of_ts, sample_split, anomaly_score, if_model_version
        FROM candidates
        WHERE choice_rank = 1
    """


def verify_model_parity(
    connection: duckdb.DuckDBPyConnection,
    config: dict[str, Any],
    if_artifact: dict[str, Any],
    graph_model: Any,
) -> dict[str, float | int]:
    if_columns = list(if_artifact["feature_cols"])
    train = _sql_path(config["artifacts"]["isolation_forest_train_features"]["path"])
    if_scores_path = _sql_path(config["artifacts"]["isolation_forest_scores"]["path"])
    if_match = _feature_match("s", "f", if_columns)
    select_if = ", ".join(f'f."{column}"' for column in if_columns)
    if_sample = connection.execute(
        f"""
        SELECT {select_if}, s.anomaly_score
        FROM read_parquet('{train}') f
        INNER JOIN read_parquet('{if_scores_path}') s
            ON s.account_key = f.account_key
           AND s.as_of_ts = f.as_of_ts
           AND {if_match}
        LIMIT 10000
        """
    ).fetchdf()
    expected_if = if_sample.pop("anomaly_score").to_numpy(dtype=np.float64)
    actual_if = isolation_forest_scores(
        if_artifact,
        if_sample.to_numpy(dtype=np.float64),
    )
    if_diff = np.abs(actual_if - expected_if)

    graph_columns = GRAPH_FEATURE_COLUMNS + DETECTOR_FEATURE_COLUMNS
    graph_modeling = _sql_path(config["artifacts"]["graph_modeling"]["path"])
    graph_scores_path = _sql_path(config["artifacts"]["graph_scores"]["path"])
    select_graph = ", ".join(f'm."{column}"' for column in graph_columns)
    graph_sample = connection.execute(
        f"""
        SELECT {select_graph}, s.graph_score
        FROM read_parquet('{graph_modeling}') m
        INNER JOIN read_parquet('{graph_scores_path}') s USING (account_key, as_of_ts)
        ORDER BY m.as_of_ts, m.account_key
        LIMIT 10000
        """
    ).fetchdf()
    expected_graph = graph_sample.pop("graph_score").to_numpy(dtype=np.float64)
    actual_graph = np.asarray(
        graph_model.predict_proba(graph_sample.to_numpy(dtype=np.float32))[:, 1],
        dtype=np.float64,
    )
    graph_diff = np.abs(actual_graph - expected_graph)

    result = {
        "sample_rows": 10000,
        "isolation_forest_max_abs_diff": float(if_diff.max()),
        "graph_max_abs_diff": float(graph_diff.max()),
    }
    if result["isolation_forest_max_abs_diff"] > 1e-12:
        raise ValueError(f"Isolation Forest handoff scores do not reproduce: {result}")
    if result["graph_max_abs_diff"] > 1e-12:
        raise ValueError(f"Graph handoff scores do not reproduce: {result}")
    return result


def _score_arrays(
    connection: duckdb.DuckDBPyConnection,
    split: str,
) -> tuple[np.ndarray, np.ndarray]:
    frame = connection.execute(
        """
        SELECT f.risk_score, m.target_laundering
        FROM fusion_work f
        INNER JOIN graph_modeling m USING (account_key, as_of_ts)
        WHERE f.sample_split = ?
        ORDER BY f.as_of_ts, f.account_key
        """,
        [split],
    ).fetchnumpy()
    return (
        np.asarray(frame["risk_score"], dtype=np.float64),
        np.asarray(frame["target_laundering"], dtype=np.uint8),
    )


def select_fusion_weights(
    *,
    if_percentile: np.ndarray,
    graph_percentile: np.ndarray,
    fusion_complete: np.ndarray,
    labels: np.ndarray,
    minimum_component_weight: float,
    step: float,
    alert_budget_rate: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Select non-zero component weights on validation only."""
    if not 0 < minimum_component_weight < 0.5:
        raise ValueError("minimum_component_weight must be in (0, 0.5)")
    if not 0 < step <= 0.5:
        raise ValueError("weight selection step must be in (0, 0.5]")
    values = np.arange(
        minimum_component_weight,
        1.0 - minimum_component_weight + step / 2,
        step,
    )
    candidates: list[dict[str, Any]] = []
    for if_weight in values:
        if_weight = round(float(if_weight), 10)
        graph_weight = 1.0 - if_weight
        scores = np.where(
            fusion_complete,
            if_weight * if_percentile + graph_weight * graph_percentile,
            graph_percentile,
        )
        selected = select_threshold_on_validation(
            labels,
            scores,
            max_alert_rate=alert_budget_rate,
        )
        candidates.append(
            {
                "isolation_forest_weight": if_weight,
                "graph_weight": graph_weight,
                **selected,
            }
        )
    winner = max(
        candidates,
        key=lambda item: (
            float(item["f1"]),
            float(item["precision"]),
            float(item["recall"]),
            -abs(float(item["isolation_forest_weight"]) - 0.5),
        ),
    )
    weights = {
        "isolation_forest": float(winner["isolation_forest_weight"]),
        "graph": float(winner["graph_weight"]),
    }
    return weights, {
        "method": "validation_grid",
        "minimum_component_weight": minimum_component_weight,
        "step": step,
        "selected": winner,
        "candidates": candidates,
    }


def build_release(
    config: dict[str, Any],
    *,
    bundle_out: Path,
    scores_out: Path,
    report_out: Path,
    checksums: bool,
) -> dict[str, Any]:
    validated = validate_artifacts(config, checksums=checksums)
    if_artifact = _load_if_artifact(_resolve(config["artifacts"]["isolation_forest_model"]["path"]))
    graph_model = load_graph_model_compat(_resolve(config["artifacts"]["graph_model"]["path"]))
    graph_columns = GRAPH_FEATURE_COLUMNS + DETECTOR_FEATURE_COLUMNS
    if int(getattr(graph_model, "n_features_in_", -1)) != len(graph_columns):
        raise ValueError("Graph model does not match the 18-column frozen feature contract")

    quantile_count = int(config["normalization"]["quantile_count"])
    weights = {key: float(value) for key, value in config["weights"].items()}
    weight_total = sum(weights.values())
    weights = {key: value / weight_total for key, value in weights.items()}
    alert_budget_rate = float(config["validation"]["alert_budget_rate"])
    precision_k = int(config["validation"]["precision_k"])

    scores_out.parent.mkdir(parents=True, exist_ok=True)
    bundle_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fin07_fusion_") as temp_dir:
        database = Path(temp_dir) / "fusion.duckdb"
        connection = duckdb.connect(str(database))
        connection.execute("SET TimeZone='UTC'")
        connection.execute("SET threads=4")
        connection.execute("SET memory_limit='2GB'")
        connection.execute(f"SET temp_directory='{Path(temp_dir).as_posix()}'")
        try:
            parity = verify_model_parity(connection, config, if_artifact, graph_model)
            connection.execute(
                "CREATE TABLE canonical_if AS " + canonical_if_sql(config, list(if_artifact["feature_cols"]))
            )
            canonical_stats = connection.execute(
                """
                SELECT
                    COUNT(*) AS rows,
                    COUNT(DISTINCT (account_key, as_of_ts)) AS unique_keys,
                    COUNT(*) FILTER (WHERE sample_split = 'train') AS train_rows,
                    COUNT(*) FILTER (WHERE sample_split = 'val') AS val_rows,
                    COUNT(*) FILTER (WHERE sample_split = 'test') AS test_rows
                FROM canonical_if
                """
            ).fetchone()
            if canonical_stats[0] != canonical_stats[1]:
                raise ValueError(f"canonical IF scores still contain duplicate keys: {canonical_stats}")

            graph_scores_path = _sql_path(config["artifacts"]["graph_scores"]["path"])
            graph_modeling_path = _sql_path(config["artifacts"]["graph_modeling"]["path"])
            connection.execute(f"CREATE VIEW graph_scores AS SELECT * FROM read_parquet('{graph_scores_path}')")
            connection.execute(f"CREATE VIEW graph_modeling AS SELECT * FROM read_parquet('{graph_modeling_path}')")
            if_train_scores = connection.execute(
                "SELECT anomaly_score FROM canonical_if WHERE sample_split='train'"
            ).fetchnumpy()["anomaly_score"]
            graph_train_scores = connection.execute(
                "SELECT graph_score FROM graph_scores WHERE sample_split='train'"
            ).fetchnumpy()["graph_score"]
            if_calibration = fit_percentile_calibration(
                if_train_scores,
                quantile_count=quantile_count,
            )
            graph_calibration = fit_percentile_calibration(
                graph_train_scores,
                quantile_count=quantile_count,
            )
            connection.register(
                "if_calibration",
                pd.DataFrame(
                    {
                        "raw_score": if_calibration.score_knots,
                        "percentile": if_calibration.percentiles,
                    }
                ),
            )
            connection.register(
                "graph_calibration",
                pd.DataFrame(
                    {
                        "raw_score": graph_calibration.score_knots,
                        "percentile": graph_calibration.percentiles,
                    }
                ),
            )

            if_weight = weights["isolation_forest"]
            graph_weight = weights["graph"]
            fusion_version = str(config["fusion_version"]).replace("'", "''")
            connection.execute(
                f"""
                CREATE TABLE fusion_work AS
                WITH base AS (
                    SELECT
                        g.account_key,
                        g.as_of_ts,
                        '7d'::VARCHAR AS "window",
                        g.sample_split,
                        i.anomaly_score AS isolation_forest_raw_score,
                        g.graph_score AS graph_raw_score,
                        i.if_model_version,
                        'graph_histgb_hien_v1'::VARCHAR AS graph_model_version,
                        g.fan_in_hit,
                        g.fan_out_hit,
                        g.gather_scatter_hit,
                        g.cycle_hit
                    FROM graph_scores g
                    LEFT JOIN canonical_if i USING (account_key, as_of_ts, sample_split)
                ),
                with_if_percentile AS (
                    SELECT b.*, COALESCE(c.percentile, 0.0) AS isolation_forest_percentile
                    FROM base b
                    ASOF LEFT JOIN if_calibration c
                        ON b.isolation_forest_raw_score >= c.raw_score
                ),
                normalized AS (
                    SELECT b.*, COALESCE(c.percentile, 0.0) AS graph_percentile
                    FROM with_if_percentile b
                    ASOF LEFT JOIN graph_calibration c
                        ON b.graph_raw_score >= c.raw_score
                ),
                contributed AS (
                    SELECT
                        *,
                        CASE WHEN isolation_forest_raw_score IS NULL THEN 0.0
                             ELSE {if_weight} * isolation_forest_percentile
                                  / ({graph_weight} + {if_weight}) END
                            AS isolation_forest_contribution,
                        {graph_weight} * graph_percentile
                            / ({graph_weight} + CASE WHEN isolation_forest_raw_score IS NULL
                                                    THEN 0.0 ELSE {if_weight} END)
                            AS graph_contribution
                    FROM normalized
                )
                SELECT
                    account_key,
                    as_of_ts,
                    "window",
                    sample_split,
                    isolation_forest_raw_score,
                    graph_raw_score,
                    isolation_forest_percentile,
                    graph_percentile,
                    isolation_forest_contribution,
                    graph_contribution,
                    LEAST(1.0, GREATEST(0.0,
                        isolation_forest_contribution + graph_contribution)) AS risk_score,
                    isolation_forest_raw_score IS NOT NULL AS fusion_complete,
                    CASE WHEN isolation_forest_raw_score IS NULL THEN 1 ELSE 2 END
                        AS component_count,
                    if_model_version,
                    graph_model_version,
                    '{fusion_version}'::VARCHAR AS fusion_version,
                    fan_in_hit,
                    fan_out_hit,
                    gather_scatter_hit,
                    cycle_hit
                FROM contributed
                """
            )

            selection_config = config["weight_selection"]
            selection_frame = connection.execute(
                """
                SELECT
                    f.isolation_forest_percentile,
                    f.graph_percentile,
                    f.fusion_complete,
                    m.target_laundering
                FROM fusion_work f
                INNER JOIN graph_modeling m USING (account_key, as_of_ts)
                WHERE f.sample_split = 'val'
                ORDER BY f.as_of_ts, f.account_key
                """
            ).fetchnumpy()
            weights, weight_selection = select_fusion_weights(
                if_percentile=np.asarray(selection_frame["isolation_forest_percentile"], dtype=np.float64),
                graph_percentile=np.asarray(selection_frame["graph_percentile"], dtype=np.float64),
                fusion_complete=np.asarray(selection_frame["fusion_complete"], dtype=bool),
                labels=np.asarray(selection_frame["target_laundering"], dtype=np.uint8),
                minimum_component_weight=float(selection_config["minimum_component_weight"]),
                step=float(selection_config["step"]),
                alert_budget_rate=alert_budget_rate,
            )
            if_weight = weights["isolation_forest"]
            graph_weight = weights["graph"]
            connection.execute(
                f"""
                UPDATE fusion_work
                SET
                    isolation_forest_contribution =
                        CASE WHEN isolation_forest_raw_score IS NULL THEN 0.0
                             ELSE {if_weight} * isolation_forest_percentile
                                  / ({graph_weight} + {if_weight}) END,
                    graph_contribution =
                        {graph_weight} * graph_percentile
                        / ({graph_weight} + CASE WHEN isolation_forest_raw_score IS NULL
                                                THEN 0.0 ELSE {if_weight} END)
                """
            )
            connection.execute(
                """
                UPDATE fusion_work
                SET risk_score = LEAST(1.0, GREATEST(0.0,
                    isolation_forest_contribution + graph_contribution))
                """
            )

            validation_scores, validation_labels = _score_arrays(connection, "val")
            selected = select_threshold_on_validation(
                validation_labels,
                validation_scores,
                max_alert_rate=alert_budget_rate,
            )
            threshold = float(selected["threshold"])
            validation_metrics = evaluate_scores(
                validation_labels,
                validation_scores,
                threshold=threshold,
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )
            test_scores, test_labels = _score_arrays(connection, "test")
            test_metrics = evaluate_scores(
                test_labels,
                test_scores,
                threshold=threshold,
                precision_k=precision_k,
                alert_budget_rate=alert_budget_rate,
            )

            if scores_out.exists():
                scores_out.unlink()
            output_sql = scores_out.as_posix().replace("'", "''")
            connection.execute(
                f"""
                COPY (
                    SELECT
                        *,
                        ROUND(risk_score * 100.0, 2) AS risk_score_100,
                        risk_score >= {threshold} AS triggered,
                        {threshold}::DOUBLE AS threshold
                    FROM fusion_work
                    ORDER BY as_of_ts, account_key
                ) TO '{output_sql}'
                (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
                """
            )
            coverage_rows = connection.execute(
                """
                SELECT
                    sample_split,
                    COUNT(*) AS rows,
                    COUNT(*) FILTER (WHERE fusion_complete) AS complete_rows,
                    COUNT(*) FILTER (WHERE NOT fusion_complete) AS graph_only_rows,
                    COUNT(*) FILTER (WHERE risk_score >= ?) AS alerts
                FROM fusion_work
                GROUP BY sample_split
                ORDER BY sample_split
                """,
                [threshold],
            ).fetchall()
        finally:
            connection.close()

    provenance = {
        "source_artifacts": validated,
        "timestamp_alignment": config["timestamp_alignment"],
        "normalization": config["normalization"],
        "weight_selection": weight_selection,
        "model_parity": parity,
    }
    bundle = build_fusion_bundle(
        fusion_version=config["fusion_version"],
        isolation_forest_artifact=if_artifact,
        graph_model=graph_model,
        graph_feature_cols=graph_columns,
        if_calibration=if_calibration,
        graph_calibration=graph_calibration,
        weights=weights,
        threshold=threshold,
        provenance=provenance,
    )
    if bundle_out.exists():
        bundle_out.unlink()
    save_fusion_bundle(bundle, bundle_out)

    coverage = {
        split: {
            "rows": int(rows),
            "complete_rows": int(complete),
            "graph_only_rows": int(graph_only),
            "complete_rate": float(complete / rows),
            "alerts": int(alerts),
        }
        for split, rows, complete, graph_only, alerts in coverage_rows
    }
    report = {
        "schema_version": "fin07.fusion.release.v1",
        "fusion_version": config["fusion_version"],
        "created_at": datetime.now(tz=UTC).isoformat(),
        "policy": {
            "window": config["window"],
            "weights": weights,
            "weight_selection": weight_selection,
            "normalization": config["normalization"],
            "missing_component_policy": config["missing_component_policy"],
            "threshold_policy": "maximize validation F1 within fixed alert budget",
            "threshold": threshold,
        },
        "canonicalization": {
            "if_rows": int(canonical_stats[0]),
            "if_unique_keys": int(canonical_stats[1]),
            "train_rows": int(canonical_stats[2]),
            "val_rows": int(canonical_stats[3]),
            "test_rows": int(canonical_stats[4]),
            "timestamp_alignment_seconds": 1,
            "duplicate_resolution": "prefer the IF source split matching canonical Graph split",
        },
        "coverage": coverage,
        "validation_threshold_selection": selected,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "model_parity": parity,
        "artifacts": {
            "bundle": {
                "path": str(bundle_out.relative_to(ROOT)),
                "sha256": sha256_file(bundle_out),
                "bytes": bundle_out.stat().st_size,
            },
            "scores": {
                "path": str(scores_out.relative_to(ROOT)),
                "sha256": sha256_file(scores_out),
                "bytes": scores_out.stat().st_size,
            },
            "sources": validated,
        },
    }
    report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = _resolve(args.config)
    report = build_release(
        load_config(config_path),
        bundle_out=_resolve(args.bundle_out),
        scores_out=_resolve(args.scores_out),
        report_out=_resolve(args.report_out),
        checksums=not args.skip_checksums,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
