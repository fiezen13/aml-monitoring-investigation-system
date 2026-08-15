#!/usr/bin/env python3
"""Load the audited currency-native HI-Medium test release into PostgreSQL.

The loader refuses to merge with an existing business population.  It is
intended to run immediately after a clean PostgreSQL reset, validates every
declared artifact checksum, and only publishes a release after row-count
checks pass.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.models.currency_native_edge import load_bundle  # noqa: E402

DEFAULT_DB = ROOT / "data/processed/hi_medium.duckdb"
DEFAULT_SCORES = ROOT / "data/processed/edge-policy-v1/hi_medium_test_scores.parquet"
DEFAULT_REPORT = ROOT / "reports/edge-benchmark/hi_medium_currency_native_policy_v1.json"
DEFAULT_MODEL = ROOT / "models/fin07_currency_native_policy_edge_v1.joblib"
DATASET = "IBM AML HI-Medium currency-native"
SOURCE_FILE = "HI-Medium_Trans.csv"


@dataclass(frozen=True)
class ReleasePlan:
    release_id: str
    model_version: str
    model_sha256: str
    scores_sha256: str
    source_database_sha256: str
    trained_at: str
    evaluated_at: str
    threshold: float
    transaction_rows: int
    positive_rows: int
    triggered_rows: int
    account_rows: int
    feature_count: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _psycopg_url(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL must use PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def _export_gzip(duck: duckdb.DuckDBPyConnection, query: str, destination: Path) -> None:
    duck.execute(
        f"COPY ({query}) TO '{_sql_path(destination)}' "
        "(FORMAT CSV, HEADER FALSE, NULL '\\N', COMPRESSION GZIP)"
    )


def _copy_gzip(pg: psycopg.Connection[Any], copy_sql: str, source: Path) -> None:
    with pg.cursor().copy(copy_sql) as copy, gzip.open(source, "rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            copy.write(chunk)


def build_release_plan(
    db_path: Path,
    scores_path: Path,
    report_path: Path,
    model_path: Path,
) -> tuple[ReleasePlan, dict[str, Any], dict[str, Any]]:
    for path in (db_path, scores_path, report_path, model_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema_version") != "fin07.currency_native_edge.benchmark.v1":
        raise ValueError("unsupported benchmark report")
    if report.get("status") != "complete":
        raise ValueError(f"benchmark is not complete: {report.get('status')}")
    if report.get("test_over_seeds", {}).get("count") != 5:
        raise ValueError("canonical release requires five benchmark seeds")

    bundle = load_bundle(model_path, require_runtime_match=False)
    model_version = str(report["model_version"])
    if bundle["model_version"] != model_version:
        raise ValueError("model version differs between report and bundle")

    model_sha = sha256_file(model_path)
    scores_sha = sha256_file(scores_path)
    declared_model = report["artifacts"]["model"]
    declared_scores = report["artifacts"]["test_scores"]
    if model_sha != declared_model["sha256"] or model_path.name != Path(declared_model["path"]).name:
        raise ValueError("model artifact checksum/path differs from report")
    if scores_sha != declared_scores["sha256"] or scores_path.name != Path(declared_scores["path"]).name:
        raise ValueError("score artifact checksum/path differs from report")

    source_sha = sha256_file(db_path)
    provenance = bundle["provenance"]
    if source_sha != provenance["source_database_sha256"]:
        raise ValueError("source DuckDB checksum differs from trained model provenance")

    duck = duckdb.connect()
    try:
        score_path = _sql_path(scores_path)
        row = duck.execute(
            f"""
            SELECT count(*), count(*) FILTER (WHERE target_laundering=1),
                   count(*) FILTER (WHERE triggered), count(DISTINCT model_version),
                   min(threshold), max(threshold),
                   count(DISTINCT account_key)
              FROM (
                SELECT *, from_account_key AS account_key FROM read_parquet('{score_path}')
                UNION ALL
                SELECT *, to_account_key AS account_key FROM read_parquet('{score_path}')
              ) endpoints
            """
        ).fetchone()
        # Counts are doubled by the endpoint UNION except account cardinality.
        tx = duck.execute(
            f"""SELECT count(*), count(*) FILTER (WHERE target_laundering=1),
                       count(*) FILTER (WHERE triggered), count(DISTINCT model_version),
                       min(threshold), max(threshold)
                  FROM read_parquet('{score_path}')"""
        ).fetchone()
    finally:
        duck.close()
    assert row is not None and tx is not None
    transaction_rows, positive_rows, triggered_rows, versions, threshold_min, threshold_max = tx
    account_rows = int(row[6])
    primary = report["test_primary_seed"]
    expected = (int(primary["rows"]), int(primary["positives"]), int(primary["alerts"]))
    actual = (int(transaction_rows), int(positive_rows), int(triggered_rows))
    if actual != expected:
        raise ValueError(f"score population differs from report: actual={actual}, expected={expected}")
    if versions != 1 or abs(float(threshold_min) - float(threshold_max)) > 1e-15:
        raise ValueError("score parquet mixes model versions or thresholds")
    if abs(float(threshold_min) - float(bundle["threshold"])) > 1e-15:
        raise ValueError("score threshold differs from model bundle")

    plan = ReleasePlan(
        release_id=f"REL-EDGE-{model_sha[:16]}",
        model_version=model_version,
        model_sha256=model_sha,
        scores_sha256=scores_sha,
        source_database_sha256=source_sha,
        trained_at=str(provenance["trained_at"]),
        evaluated_at=str(report["created_at"]),
        threshold=float(threshold_min),
        transaction_rows=int(transaction_rows),
        positive_rows=int(positive_rows),
        triggered_rows=int(triggered_rows),
        account_rows=account_rows,
        feature_count=len(report["features"]),
    )
    return plan, report, bundle


def _require_clean_schema(pg: psycopg.Connection[Any]) -> None:
    schema_ok = pg.execute(
        """
        SELECT to_regclass('public.edge_model_release') IS NOT NULL,
               to_regclass('public.transaction_model_score') IS NOT NULL
        """
    ).fetchone()
    if schema_ok != (True, True):
        raise RuntimeError("schema 013 is required; run `make migrate`")
    counts = pg.execute(
        """SELECT (SELECT count(*) FROM customer),
                  (SELECT count(*) FROM transaction),
                  (SELECT count(*) FROM alert),
                  (SELECT count(*) FROM edge_model_release)"""
    ).fetchone()
    if counts != (0, 0, 0, 0):
        raise RuntimeError(
            "refusing to merge the new release into existing business data; "
            f"counts={counts}. Reset PostgreSQL first."
        )


def _start_release(
    pg: psycopg.Connection[Any],
    plan: ReleasePlan,
    report: dict[str, Any],
) -> None:
    pg.execute(
        """
        INSERT INTO edge_model_release (
          release_id, model_version, dataset, split, model_sha256, scores_sha256,
          source_database_sha256, threshold, transaction_rows, positive_rows,
          triggered_rows, feature_count, benchmark, policy, status, trained_at
        ) VALUES (%s, %s, %s, 'test', %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, 'loading', %s)
        """,
        (
            plan.release_id,
            plan.model_version,
            DATASET,
            plan.model_sha256,
            plan.scores_sha256,
            plan.source_database_sha256,
            plan.threshold,
            plan.transaction_rows,
            plan.positive_rows,
            plan.triggered_rows,
            plan.feature_count,
            Jsonb(
                {
                    "primary_seed": report["test_primary_seed"],
                    "over_seeds": report["test_over_seeds"],
                    "operating_points": report["operating_points"],
                }
            ),
            Jsonb(report["policy"]),
            plan.trained_at,
        ),
    )
    pg.commit()


def _load_accounts(
    pg: psycopg.Connection[Any],
    duck: duckdb.DuckDBPyConnection,
    score_path: str,
    temp_dir: Path,
    plan: ReleasePlan,
) -> None:
    print(f"[1/4] Loading {plan.account_rows:,} accounts", flush=True)
    archive = temp_dir / "accounts.csv.gz"
    _export_gzip(
        duck,
        f"""
        WITH endpoints AS (
          SELECT from_account_key AS account_key, occurred_at FROM read_parquet('{score_path}')
          UNION ALL
          SELECT to_account_key AS account_key, occurred_at FROM read_parquet('{score_path}')
        )
        SELECT account_key,
               'CUST-HI-' || substr(md5(account_key), 1, 20),
               split_part(account_key, ':', 1),
               split_part(account_key, ':', 2),
               CAST(min(occurred_at) AS DATE)
          FROM endpoints GROUP BY account_key ORDER BY account_key
        """,
        archive,
    )
    pg.execute(
        """CREATE TEMP TABLE stage_edge_account (
             account_key TEXT, customer_id TEXT, bank_code TEXT,
             account_number TEXT, opened_at DATE
           )"""
    )
    _copy_gzip(pg, "COPY stage_edge_account FROM STDIN WITH (FORMAT CSV, NULL '\\N')", archive)
    staged = int(pg.execute("SELECT count(*) FROM stage_edge_account").fetchone()[0])
    if staged != plan.account_rows:
        raise RuntimeError(f"account stage count mismatch: {staged} != {plan.account_rows}")
    pg.execute(
        """
        INSERT INTO customer (
          customer_id, customer_type, prototype, occupation, declared_income_band,
          expected_monthly_volume, registered_country, onboarding_date, risk_rating
        )
        SELECT customer_id, 'organisation', 'enterprise',
               'KYC unavailable - IBM AML HI-Medium', 'kyc_unavailable',
               0, 'XX', opened_at, 'medium'
          FROM stage_edge_account
        """
    )
    pg.execute(
        """
        INSERT INTO account (account_key, customer_id, bank_code, account_number, opened_at, status)
        SELECT account_key, customer_id, bank_code, account_number, opened_at, 'active'
          FROM stage_edge_account
        """
    )
    pg.execute("DROP TABLE stage_edge_account")
    pg.commit()
    archive.unlink()


def _load_transactions_and_scores(
    pg: psycopg.Connection[Any],
    duck: duckdb.DuckDBPyConnection,
    score_path: str,
    temp_dir: Path,
    plan: ReleasePlan,
) -> None:
    missing = int(
        duck.execute(
            f"""
            SELECT count(*) FROM read_parquet('{score_path}') s
            LEFT JOIN "transaction" src USING (transaction_id)
            WHERE src.transaction_id IS NULL
            """
        ).fetchone()[0]
    )
    if missing:
        raise RuntimeError(f"{missing:,} scored transaction ids are absent from source DuckDB")

    print(f"[2/4] Loading {plan.transaction_rows:,} scored transactions", flush=True)
    archive = temp_dir / "transactions.csv.gz"
    _export_gzip(
        duck,
        f"""
        SELECT s.transaction_id, s.occurred_at, s.from_account_key, s.to_account_key,
               s.amount_paid_orig, s.payment_currency,
               s.amount_received_orig, s.receiving_currency,
               coalesce(src.channel, 'UNKNOWN'), CAST(s.target_laundering AS BOOLEAN),
               s.score, s.threshold, s.triggered
          FROM read_parquet('{score_path}') s
          JOIN "transaction" src USING (transaction_id)
         ORDER BY s.occurred_at, s.transaction_id
        """,
        archive,
    )
    pg.execute(
        """
        CREATE TEMP TABLE stage_edge_transaction (
          source_transaction_id TEXT, occurred_at TIMESTAMPTZ,
          from_account_key TEXT, to_account_key TEXT,
          amount NUMERIC(38,18), currency TEXT,
          amount_received NUMERIC(38,18), receiving_currency TEXT,
          channel TEXT, label_laundering BOOLEAN,
          model_score DOUBLE PRECISION, threshold DOUBLE PRECISION, triggered BOOLEAN
        )
        """
    )
    _copy_gzip(pg, "COPY stage_edge_transaction FROM STDIN WITH (FORMAT CSV, NULL '\\N')", archive)
    staged = int(pg.execute("SELECT count(*) FROM stage_edge_transaction").fetchone()[0])
    if staged != plan.transaction_rows:
        raise RuntimeError(f"transaction stage count mismatch: {staged} != {plan.transaction_rows}")
    pg.execute(
        """
        INSERT INTO transaction (
          occurred_at, from_account_key, to_account_key, amount, currency,
          amount_received, receiving_currency, channel, remarks, dataset_split,
          source_transaction_id, source_dataset, source_file, ingested_at
        )
        SELECT occurred_at, from_account_key, to_account_key, amount, currency,
               amount_received, receiving_currency, channel, '', 'test',
               source_transaction_id, %s, %s, now()
          FROM stage_edge_transaction
        """,
        (DATASET, SOURCE_FILE),
    )
    pg.execute(
        """
        INSERT INTO label.label_laundering (transaction_id, is_laundering)
        SELECT t.transaction_id, s.label_laundering
          FROM stage_edge_transaction s
          JOIN transaction t USING (source_transaction_id)
        """
    )
    print(f"[3/4] Loading {plan.transaction_rows:,} scores and {plan.triggered_rows:,} alerts", flush=True)
    pg.execute(
        """
        INSERT INTO transaction_model_score (
          release_id, transaction_id, model_score, threshold, triggered
        )
        SELECT %s, t.transaction_id, s.model_score, s.threshold, s.triggered
          FROM stage_edge_transaction s
          JOIN transaction t USING (source_transaction_id)
        """,
        (plan.release_id,),
    )
    pg.execute(
        """
        INSERT INTO alert (
          alert_id, account_key, transaction_id, typology_code, detector,
          risk_score, status, case_id, created_at
        )
        SELECT 'ALT-EDGE-' || substr(md5(%s || '|' || s.source_transaction_id), 1, 20),
               s.from_account_key, t.transaction_id, 'T02', 'ml',
               round((s.model_score * 100)::numeric, 2), 'open', NULL, s.occurred_at
          FROM stage_edge_transaction s
          JOIN transaction t USING (source_transaction_id)
         WHERE s.triggered
        """,
        (plan.release_id,),
    )
    pg.execute(
        """
        INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
        SELECT 'ALT-EDGE-' || substr(md5(%s || '|' || s.source_transaction_id), 1, 20),
               reason.factor_code, reason.factor_label, reason.contribution, reason.weight
          FROM stage_edge_transaction s
          CROSS JOIN LATERAL (
            VALUES
              ('MODEL_SCORE', 'Currency-native transaction model score',
               round((s.model_score * 100)::numeric, 2), 1.00::numeric),
              ('THRESHOLD_MARGIN', 'Margin over validation-selected threshold',
               round(((s.model_score-s.threshold) * 100)::numeric, 2), 1.00::numeric),
              ('POLICY_CONTRACT', 'Native amounts; train-only per-currency normalization',
               0.00::numeric, 0.00::numeric)
          ) reason(factor_code, factor_label, contribution, weight)
         WHERE s.triggered
        """,
        (plan.release_id,),
    )
    pg.execute("DROP TABLE stage_edge_transaction")
    pg.commit()
    archive.unlink()


def _publish_release(
    pg: psycopg.Connection[Any],
    plan: ReleasePlan,
    report: dict[str, Any],
) -> dict[str, int]:
    row = pg.execute(
        """
        SELECT (SELECT count(*) FROM account),
               (SELECT count(*) FROM transaction),
               (SELECT count(*) FROM transaction_model_score WHERE release_id=%s),
               (SELECT count(*) FROM transaction_model_score WHERE release_id=%s AND triggered),
               (SELECT count(*) FROM alert),
               (SELECT count(*) FROM alert_reason)
        """,
        (plan.release_id, plan.release_id),
    ).fetchone()
    assert row is not None
    keys = ("accounts", "transactions", "scores", "triggered", "alerts", "reasons")
    counts = {key: int(value) for key, value in zip(keys, row, strict=True)}
    expected = {
        "accounts": plan.account_rows,
        "transactions": plan.transaction_rows,
        "scores": plan.transaction_rows,
        "triggered": plan.triggered_rows,
        "alerts": plan.triggered_rows,
        "reasons": plan.triggered_rows * 3,
    }
    if counts != expected:
        raise RuntimeError(f"published counts mismatch: actual={counts}, expected={expected}")

    pg.execute("UPDATE edge_model_release SET status='retired' WHERE status='active'")
    pg.execute(
        "UPDATE edge_model_release SET status='active', activated_at=now() WHERE release_id=%s",
        (plan.release_id,),
    )
    primary = report["test_primary_seed"]
    over_seeds = report["test_over_seeds"]
    metrics = {
        "f1_mean_5_seeds": over_seeds["f1_mean"],
        "f1_sample_std_5_seeds": over_seeds["f1_sample_std"],
        "f1_primary_seed": primary["f1"],
        "pr_auc_primary_seed": primary["pr_auc"],
        "precision_primary_seed": primary["precision"],
        "recall_primary_seed": primary["recall"],
    }
    for metric_name, metric_value in metrics.items():
        pg.execute(
            """
            INSERT INTO fc.benchmark_result (
              result_id, task_id, scenario_package, model_version, split,
              metric_name, metric_value, target_value, evaluated_at
            ) VALUES (%s, 'FIN-07-ML-CURRENCY-NATIVE', 'HI-Medium', %s, 'test',
                      %s, %s, NULL, %s)
            """,
            (
                f"BENCH-EDGE-{hashlib.sha1(metric_name.encode()).hexdigest()[:16]}",
                plan.model_version,
                metric_name,
                metric_value,
                plan.evaluated_at,
            ),
        )
    for metric_name, metric_value in {
        "alert_volume": plan.triggered_rows,
        "alert_rate": primary["alert_rate"],
    }.items():
        pg.execute(
            """
            INSERT INTO fc.model_monitor (
              monitor_id, model_version, observed_at, metric_name,
              metric_value, drift_score, status
            ) VALUES (%s, %s, now(), %s, %s, NULL, 'ok')
            """,
            (
                f"MON-EDGE-{hashlib.sha1(metric_name.encode()).hexdigest()[:16]}",
                plan.model_version,
                metric_name,
                metric_value,
            ),
        )
    pg.execute("ANALYZE account")
    pg.execute("ANALYZE transaction")
    pg.execute("ANALYZE transaction_model_score")
    pg.execute("ANALYZE alert")
    pg.commit()
    return counts


def load_release(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _absolute(args.db)
    scores_path = _absolute(args.scores)
    report_path = _absolute(args.report)
    model_path = _absolute(args.model)
    print("Validating model, scores, source database, and benchmark report...", flush=True)
    plan, report, _bundle = build_release_plan(db_path, scores_path, report_path, model_path)
    if args.dry_run:
        return {"status": "validated", "dry_run": True, "plan": asdict(plan)}

    pg = psycopg.connect(_psycopg_url(args.database_url or get_settings().database_url))
    try:
        pg.execute("SET TIME ZONE 'UTC'")
        pg.execute("SET synchronous_commit=off")
        _require_clean_schema(pg)
        _start_release(pg, plan, report)
        duck = duckdb.connect(str(db_path), read_only=True)
        try:
            duck.execute("SET TimeZone='UTC'")
            duck.execute("SET threads=4")
            score_path = _sql_path(scores_path)
            with tempfile.TemporaryDirectory(prefix="fin07-edge-load-") as temp_name:
                temp_dir = Path(temp_name)
                _load_accounts(pg, duck, score_path, temp_dir, plan)
                _load_transactions_and_scores(pg, duck, score_path, temp_dir, plan)
        finally:
            duck.close()
        print("[4/4] Verifying counts and activating release", flush=True)
        counts = _publish_release(pg, plan, report)
        return {"status": "active", "release_id": plan.release_id, **counts}
    except Exception as exc:
        pg.rollback()
        try:
            pg.execute(
                "UPDATE edge_model_release SET status='failed' WHERE release_id=%s",
                (plan.release_id,),
            )
            pg.commit()
        except Exception:
            pg.rollback()
        raise RuntimeError(f"release load failed: {exc}") from exc
    finally:
        pg.close()


def main(argv: list[str] | None = None) -> int:
    result = load_release(parse_args(argv))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
