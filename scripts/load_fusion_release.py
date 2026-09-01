#!/usr/bin/env python3
"""Bulk-load canonical LI-Small and the frozen fusion-v2 champion into PostgreSQL.

The loader is restartable and idempotent.  It imports the full canonical
transaction population, then persists only the latest deployment snapshot as
durable feature/detection rows and analyst-facing alerts.
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
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.services.typology_assignment import assign_from_graph_motifs  # noqa: E402

DEFAULT_DB = ROOT / "data/processed/aml.duckdb"
DEFAULT_SCORES = ROOT / "data/processed/fusion-v2/fusion_scores.parquet"
DEFAULT_MANIFEST = ROOT / "reports/fusion-v2/manifest.json"
DEFAULT_BUNDLE = ROOT / "models/fin07_if_graph_fusion_v2.joblib"
SOURCE_DATASET = "ibm-aml-li-small-canonical-v1"
SOURCE_FILE = "LI-Small_Trans.csv"
FEATURE_DEFINITION_VERSION = "fusion_feature_spec_v2"


@dataclass(frozen=True)
class ReleasePlan:
    batch_id: str
    model_version: str
    model_sha256: str
    source_sha256: str
    champion: str
    champion_threshold: float
    transaction_rows: int
    account_rows: int
    snapshot_time: str
    snapshot_rows: int
    triggered_rows: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL (the SQLAlchemy +psycopg form is accepted)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate artifacts without writing PostgreSQL")
    return parser.parse_args(argv)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 20) -> str:
    raw = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]


def _absolute(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _manifest_artifact(manifest: dict[str, Any], name: str) -> tuple[Path, str]:
    declaration = manifest["artifacts"][name]
    return _absolute(Path(declaration["path"])), str(declaration["sha256"])


def build_release_plan(
    *,
    db_path: Path,
    scores_path: Path,
    manifest_path: Path,
    bundle_path: Path,
) -> ReleasePlan:
    paths = (db_path, scores_path, manifest_path, bundle_path)
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "fin07.fusion.release.v2":
        raise ValueError("unsupported release manifest")
    champion = str(manifest.get("champion"))
    if champion not in {"graph", "fusion"}:
        raise ValueError(f"unsupported champion: {champion}")

    declared_db = str(manifest["input_artifacts"]["duckdb"]["sha256"])
    declared_scores_path, declared_scores = _manifest_artifact(manifest, "scores")
    declared_bundle_path, declared_bundle = _manifest_artifact(manifest, "bundle")
    checks = (
        ("DuckDB", db_path, declared_db),
        ("scores", scores_path, declared_scores),
        ("bundle", bundle_path, declared_bundle),
    )
    for label, path, expected in checks:
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"{label} checksum mismatch: expected={expected}, actual={actual}")
    if declared_scores_path != scores_path.resolve():
        raise ValueError(f"scores path differs from manifest: {declared_scores_path}")
    if declared_bundle_path != bundle_path.resolve():
        raise ValueError(f"bundle path differs from manifest: {declared_bundle_path}")

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        transaction_rows = int(connection.execute('SELECT count(*) FROM "transaction"').fetchone()[0])
        account_rows = int(connection.execute("SELECT count(*) FROM account").fetchone()[0])
    finally:
        connection.close()
    if transaction_rows != 6_119_572 or account_rows != 576_781:
        raise ValueError(
            f"canonical LI-Small population mismatch: transactions={transaction_rows}, accounts={account_rows}"
        )

    score_connection = duckdb.connect()
    try:
        latest, rows, triggered, champions, windows = score_connection.execute(
            """
            SELECT max(as_of_ts),
                   count(*) FILTER (WHERE as_of_ts = latest.latest_ts),
                   count(*) FILTER (WHERE as_of_ts = latest.latest_ts AND triggered),
                   count(DISTINCT champion) FILTER (WHERE as_of_ts = latest.latest_ts),
                   count(DISTINCT "window") FILTER (WHERE as_of_ts = latest.latest_ts)
              FROM read_parquet(?)
              CROSS JOIN (SELECT max(as_of_ts) AS latest_ts FROM read_parquet(?)) latest
            """,
            [str(scores_path), str(scores_path)],
        ).fetchone()
        score_champion, score_window = score_connection.execute(
            'SELECT any_value(champion), any_value("window") FROM read_parquet(?) WHERE as_of_ts = ?',
            [str(scores_path), latest],
        ).fetchone()
    finally:
        score_connection.close()
    deployment = manifest["deployment_snapshot"]
    if int(rows) != int(deployment["rows"]) or int(triggered) != int(deployment["triggered"]):
        raise ValueError("deployment snapshot counts differ from manifest")
    if champions != 1 or score_champion != champion or windows != 1 or score_window != "7d":
        raise ValueError("deployment scores contain inconsistent champion/window values")

    fusion_version = str(manifest["fusion_version"])
    model_version = f"{fusion_version}:{champion}"
    source_sha256 = declared_db
    return ReleasePlan(
        batch_id=stable_id("BAT-FUS-", source_sha256, "7d", model_version, length=16),
        model_version=model_version,
        model_sha256=declared_bundle,
        source_sha256=source_sha256,
        champion=champion,
        champion_threshold=float(manifest["champion_threshold"]),
        transaction_rows=transaction_rows,
        account_rows=account_rows,
        snapshot_time=latest.isoformat(),
        snapshot_rows=int(rows),
        triggered_rows=int(triggered),
    )


def _psycopg_url(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL must use PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def _export_gzip(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    destination: Path,
) -> None:
    connection.execute(
        f"COPY ({query}) TO '{_sql_path(destination)}' (FORMAT CSV, HEADER FALSE, NULL '\\N', COMPRESSION GZIP)"
    )


def _copy_gzip(pg: psycopg.Connection[Any], copy_sql: str, source: Path) -> None:
    with pg.cursor().copy(copy_sql) as copy, gzip.open(source, "rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            copy.write(chunk)


def _require_schema(pg: psycopg.Connection[Any]) -> None:
    row = pg.execute(
        """
        SELECT to_regclass('public.behavior_batch') IS NOT NULL,
               to_regclass('public.detection_result') IS NOT NULL,
               to_regclass('public.bank') IS NOT NULL,
               EXISTS (
                 SELECT 1 FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='behavior_batch'
                    AND column_name='model_sha256'
               )
        """
    ).fetchone()
    if row != (True, True, True, True):
        raise RuntimeError("PostgreSQL schema 001-011 is required; run `make migrate`")


def _completed_counts(pg: psycopg.Connection[Any], plan: ReleasePlan) -> dict[str, int] | None:
    status = pg.execute("SELECT status FROM behavior_batch WHERE batch_id=%s", (plan.batch_id,)).fetchone()
    if status is None or status[0] != "completed":
        return None
    row = pg.execute(
        """
        SELECT
          (SELECT count(*) FROM transaction WHERE behavior_batch_id=%s),
          (SELECT count(*) FROM label.label_laundering l
             JOIN transaction t USING (transaction_id) WHERE t.behavior_batch_id=%s),
          (SELECT count(*) FROM behavior_feature_snapshot WHERE batch_id=%s),
          (SELECT count(*) FROM detection_result WHERE batch_id=%s),
          (SELECT count(*) FROM detection_result WHERE batch_id=%s AND triggered),
          (SELECT count(*) FROM detection_result WHERE batch_id=%s AND alert_id IS NOT NULL),
          (SELECT count(*) FROM alert_reason r
             JOIN detection_result d USING (alert_id) WHERE d.batch_id=%s)
        """,
        (plan.batch_id,) * 7,
    ).fetchone()
    assert row is not None
    keys = ("transactions", "labels", "snapshots", "detections", "triggered", "alerts", "reasons")
    counts = {key: int(value) for key, value in zip(keys, row, strict=True)}
    expected = {
        "transactions": plan.transaction_rows,
        "labels": plan.transaction_rows,
        "snapshots": plan.snapshot_rows,
        "detections": plan.snapshot_rows,
        "triggered": plan.triggered_rows,
        "alerts": plan.triggered_rows,
        "reasons": plan.triggered_rows * 3,
    }
    if counts != expected:
        raise RuntimeError(f"completed batch is inconsistent: actual={counts}, expected={expected}")
    return counts


def _start_batch(pg: psycopg.Connection[Any], plan: ReleasePlan) -> None:
    existing = pg.execute(
        "SELECT threshold, model_sha256 FROM behavior_batch WHERE batch_id=%s",
        (plan.batch_id,),
    ).fetchone()
    rounded_threshold = round(plan.champion_threshold, 6)
    if existing is not None:
        if abs(float(existing[0]) - rounded_threshold) > 1e-9 or existing[1] != plan.model_sha256:
            raise RuntimeError("batch id already exists with different threshold/model bytes")
    pg.execute(
        """
        INSERT INTO behavior_batch (
          batch_id, source_name, source_sha256, status, feature_window,
          model_version, model_sha256, threshold, rows_read, rows_rejected
        ) VALUES (%s, %s, %s, 'running', '7d', %s, %s, %s, %s, 0)
        ON CONFLICT (batch_id) DO UPDATE SET
          status='running', completed_at=NULL, failure_reason=NULL,
          rows_read=EXCLUDED.rows_read
        """,
        (
            plan.batch_id,
            "IBM AML LI-Small canonical + fusion v2",
            plan.source_sha256,
            plan.model_version,
            plan.model_sha256,
            rounded_threshold,
            plan.transaction_rows,
        ),
    )
    pg.commit()


def _load_accounts(
    pg: psycopg.Connection[Any],
    duck: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> None:
    print("[1/5] Exporting and loading 576,781 canonical accounts", flush=True)
    archive = temp_dir / "accounts.csv.gz"
    _export_gzip(
        duck,
        """
        SELECT account_key,
               'CUST-LI-' || substr(md5(account_key), 1, 16) AS customer_id,
               split_part(account_key, ':', 1) AS bank_code,
               split_part(account_key, ':', 2) AS account_number,
               CAST(first_seen_at AS DATE) AS opened_at
          FROM account ORDER BY account_key
        """,
        archive,
    )
    pg.execute("DROP TABLE IF EXISTS stage_fusion_account")
    pg.execute(
        """
        CREATE TEMP TABLE stage_fusion_account (
          account_key TEXT, customer_id TEXT, bank_code TEXT,
          account_number TEXT, opened_at DATE
        )
        """
    )
    _copy_gzip(
        pg,
        "COPY stage_fusion_account FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
        archive,
    )
    pg.execute(
        """
        INSERT INTO customer (
          customer_id, customer_type, prototype, occupation,
          declared_income_band, expected_monthly_volume,
          registered_country, onboarding_date, risk_rating
        )
        SELECT customer_id, 'organisation', 'enterprise',
               'KYC unavailable - IBM AML LI-Small', 'kyc_unavailable',
               0, 'XX', opened_at, 'medium'
          FROM stage_fusion_account
        ON CONFLICT (customer_id) DO NOTHING
        """
    )
    pg.execute(
        """
        INSERT INTO account (
          account_key, customer_id, bank_code, account_number, opened_at, status
        )
        SELECT account_key, customer_id, bank_code, account_number, opened_at, 'active'
          FROM stage_fusion_account
        ON CONFLICT (account_key) DO NOTHING
        """
    )
    pg.commit()
    archive.unlink()


def _load_transactions(
    pg: psycopg.Connection[Any],
    duck: duckdb.DuckDBPyConnection,
    temp_dir: Path,
    plan: ReleasePlan,
) -> None:
    print("[2/5] Exporting and loading 6,119,572 canonical transactions", flush=True)
    archive = temp_dir / "transactions.csv.gz"
    _export_gzip(
        duck,
        """
        SELECT transaction_id AS source_transaction_id,
               occurred_at, from_account_key, to_account_key,
               greatest(round(amount, 2), 0.01) AS amount, currency,
               greatest(round(amount_received, 2), 0.01) AS amount_received,
               currency AS receiving_currency,
               channel,
               CASE split WHEN 'val' THEN 'validation' ELSE split END AS dataset_split,
               CAST(label_laundering AS BOOLEAN) AS label_laundering
          FROM \"transaction\"
         ORDER BY occurred_at, transaction_id
        """,
        archive,
    )
    pg.execute("DROP TABLE IF EXISTS stage_fusion_transaction")
    pg.execute(
        """
        CREATE TEMP TABLE stage_fusion_transaction (
          source_transaction_id TEXT, occurred_at TIMESTAMPTZ,
          from_account_key TEXT, to_account_key TEXT,
          amount NUMERIC(18,2), currency CHAR(3),
          amount_received NUMERIC(18,2), receiving_currency CHAR(3),
          channel TEXT, dataset_split TEXT, label_laundering BOOLEAN
        )
        """
    )
    _copy_gzip(
        pg,
        "COPY stage_fusion_transaction FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
        archive,
    )
    pg.execute(
        """
        INSERT INTO transaction (
          occurred_at, from_account_key, to_account_key, amount, currency,
          amount_received, receiving_currency, channel, remarks, dataset_split,
          source_transaction_id, source_dataset, source_file, ingested_at,
          behavior_batch_id
        )
        SELECT occurred_at, from_account_key, to_account_key, amount, currency,
               amount_received, receiving_currency, channel, '', dataset_split,
               source_transaction_id, %s, %s, now(), %s
          FROM stage_fusion_transaction
        ON CONFLICT DO NOTHING
        """,
        (SOURCE_DATASET, SOURCE_FILE, plan.batch_id),
    )
    pg.commit()
    print("[3/5] Loading transaction ground-truth labels (evaluation only)", flush=True)
    pg.execute(
        """
        INSERT INTO label.label_laundering (transaction_id, is_laundering)
        SELECT t.transaction_id, s.label_laundering
          FROM stage_fusion_transaction s
          JOIN transaction t ON t.source_transaction_id=s.source_transaction_id
        ON CONFLICT (transaction_id) DO UPDATE
          SET is_laundering=EXCLUDED.is_laundering
        """
    )
    pg.execute("DROP TABLE stage_fusion_transaction")
    pg.commit()
    archive.unlink()


def _load_scores(
    pg: psycopg.Connection[Any],
    temp_dir: Path,
    scores_path: Path,
    plan: ReleasePlan,
) -> None:
    print(
        f"[4/5] Loading latest {plan.champion} snapshot: "
        f"{plan.snapshot_rows:,} detections / {plan.triggered_rows:,} alerts",
        flush=True,
    )
    archive = temp_dir / "scores.csv.gz"
    score_db = duckdb.connect()
    try:
        escaped_model = plan.model_version.replace("'", "''")
        escaped_scores = _sql_path(scores_path)
        _export_gzip(
            score_db,
            f"""
            WITH latest AS (
              SELECT max(as_of_ts) AS as_of_ts FROM read_parquet('{escaped_scores}')
            )
            SELECT
              'BFS-FUS-' || substr(md5(account_key || '|' ||
                CAST(CAST(epoch(s.as_of_ts) AS BIGINT) AS VARCHAR) || '|{escaped_model}'), 1, 20),
              'DET-FUS-' || substr(md5(account_key || '|' ||
                CAST(CAST(epoch(s.as_of_ts) AS BIGINT) AS VARCHAR) || '|{escaped_model}'), 1, 20),
              'ALT-FUS-' || substr(md5(account_key || '|' ||
                CAST(CAST(epoch(s.as_of_ts) AS BIGINT) AS VARCHAR) || '|{escaped_model}'), 1, 20),
              account_key, s.as_of_ts,
              isolation_forest_percentile, graph_percentile,
              isolation_forest_contribution, graph_contribution,
              fusion_score, champion_score, champion_threshold, triggered,
              fan_in_hit, fan_out_hit, gather_scatter_hit, cycle_hit,
              detector_motif_count, target_laundering
            FROM read_parquet('{escaped_scores}') s, latest
            WHERE s.as_of_ts=latest.as_of_ts
            ORDER BY account_key
            """,
            archive,
        )
    finally:
        score_db.close()

    pg.execute("DROP TABLE IF EXISTS stage_fusion_score")
    pg.execute(
        """
        CREATE TEMP TABLE stage_fusion_score (
          snapshot_id TEXT, result_id TEXT, alert_id TEXT,
          account_key TEXT, as_of_time TIMESTAMPTZ,
          if_percentile DOUBLE PRECISION, graph_percentile DOUBLE PRECISION,
          if_contribution DOUBLE PRECISION, graph_contribution DOUBLE PRECISION,
          fusion_score DOUBLE PRECISION, champion_score DOUBLE PRECISION,
          champion_threshold DOUBLE PRECISION, triggered BOOLEAN,
          fan_in_hit INTEGER, fan_out_hit INTEGER, gather_scatter_hit INTEGER,
          cycle_hit INTEGER, detector_motif_count INTEGER, target_laundering INTEGER
        )
        """
    )
    _copy_gzip(pg, "COPY stage_fusion_score FROM STDIN WITH (FORMAT CSV, NULL '\\N')", archive)
    pg.execute(
        """
        INSERT INTO behavior_feature_snapshot (
          snapshot_id, batch_id, account_key, as_of_time, feature_window,
          definition_version, model_version, features
        )
        SELECT snapshot_id, %s, account_key, as_of_time, '7d', %s, %s,
               jsonb_build_object(
                 'isolation_forest_percentile', if_percentile,
                 'graph_percentile', graph_percentile,
                 'isolation_forest_contribution', if_contribution,
                 'graph_contribution', graph_contribution,
                 'fusion_score', fusion_score,
                 'champion', %s::text,
                 'fan_in_hit', fan_in_hit, 'fan_out_hit', fan_out_hit,
                 'gather_scatter_hit', gather_scatter_hit, 'cycle_hit', cycle_hit,
                 'detector_motif_count', detector_motif_count
               )
          FROM stage_fusion_score
        ON CONFLICT (snapshot_id) DO NOTHING
        """,
        (plan.batch_id, FEATURE_DEFINITION_VERSION, plan.model_version, plan.champion),
    )
    pg.execute(
        """
        INSERT INTO alert (
          alert_id, account_key, transaction_id, typology_code, detector,
          risk_score, status, case_id, created_at
        )
        SELECT alert_id, account_key, NULL, 'T02', %s,
               round((least(greatest(champion_score, 0), 1) * 100)::numeric, 2),
               'open', NULL, as_of_time
          FROM stage_fusion_score WHERE triggered
        ON CONFLICT (alert_id) DO NOTHING
        """,
        ("graph" if plan.champion == "graph" else "ml",),
    )
    # Nhóm hành vi suy từ mẫu hình đồ thị đã trúng, thay vì đóng dấu cứng T02.
    # Luật nằm trong typologies.json; ở đây chỉ đưa tín hiệu vào.
    motif_rows = pg.execute(
        """
        SELECT alert_id, fan_in_hit, fan_out_hit, gather_scatter_hit, cycle_hit
          FROM stage_fusion_score WHERE triggered
        """
    ).fetchall()
    typology_stats = assign_from_graph_motifs(
        pg,
        (
            (
                str(row[0]),
                {
                    "fan_in_hit": row[1],
                    "fan_out_hit": row[2],
                    "gather_scatter_hit": row[3],
                    "cycle_hit": row[4],
                },
            )
            for row in motif_rows
        ),
    )
    print(
        f"      typology: {typology_stats['matched']} suy tu tin hieu, {typology_stats['fallback']} dung mac dinh",
        flush=True,
    )
    pg.execute(
        """
        INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
        SELECT alert_id, factor_code, factor_label, contribution, weight
          FROM stage_fusion_score s
          CROSS JOIN LATERAL (
            VALUES
              ('GRAPH_SIGNAL', 'Graph percentile score',
               round((s.graph_percentile * 100)::numeric, 2), 0.90::numeric),
              ('BEHAVIOR_SIGNAL', 'Isolation Forest percentile score',
               round((s.if_percentile * 100)::numeric, 2), 0.10::numeric),
              ('CHAMPION_POLICY', 'Frozen champion threshold margin',
               round((greatest(s.champion_score-s.champion_threshold, 0) * 100)::numeric, 2),
               1.00::numeric)
          ) reason(factor_code, factor_label, contribution, weight)
         WHERE s.triggered
        ON CONFLICT (alert_id, factor_code) DO NOTHING
        """
    )
    pg.execute(
        """
        INSERT INTO detection_result (
          result_id, batch_id, snapshot_id, alert_id, account_key,
          detector_id, detector_type, detector_version,
          evaluated_at, as_of_time, score, confidence, triggered, threshold,
          reason_codes, typology_candidates, feature_refs, payload
        )
        SELECT result_id, %s, snapshot_id,
               CASE WHEN triggered THEN alert_id ELSE NULL END,
               account_key, 'fin07_fusion_champion', upper(%s), %s,
               now(), as_of_time,
               round(champion_score::numeric, 6), round(champion_score::numeric, 6),
               triggered, round(champion_threshold::numeric, 6),
               jsonb_build_array(
                 jsonb_build_object('code','GRAPH_SIGNAL','contribution',graph_contribution),
                 jsonb_build_object('code','BEHAVIOR_SIGNAL','contribution',if_contribution),
                 jsonb_build_object('code','CHAMPION_POLICY','champion',%s::text)
               ),
               jsonb_build_array(jsonb_build_object(
                 'typology_id','T02','typology_version','v1','confidence',champion_score
               )),
               jsonb_build_array(jsonb_build_object(
                 'feature_set_id',%s::text,'as_of_time',as_of_time
               )),
               jsonb_build_object(
                 'schema_version','fin07.fusion.detection.v2',
                 'champion',%s::text, 'fusion_score',fusion_score,
                 'graph_percentile',graph_percentile,
                 'isolation_forest_percentile',if_percentile,
                 'target_laundering_evaluation_only',target_laundering
               )
          FROM stage_fusion_score
        ON CONFLICT (result_id) DO NOTHING
        """,
        (
            plan.batch_id,
            plan.champion,
            plan.model_version,
            plan.champion,
            FEATURE_DEFINITION_VERSION,
            plan.champion,
        ),
    )
    pg.execute("DROP TABLE stage_fusion_score")
    pg.commit()
    archive.unlink()


def _complete(pg: psycopg.Connection[Any], plan: ReleasePlan) -> dict[str, int]:
    tx_count = int(
        pg.execute("SELECT count(*) FROM transaction WHERE behavior_batch_id=%s", (plan.batch_id,)).fetchone()[0]
    )
    detection_count = int(
        pg.execute("SELECT count(*) FROM detection_result WHERE batch_id=%s", (plan.batch_id,)).fetchone()[0]
    )
    alert_count = int(
        pg.execute(
            "SELECT count(*) FROM detection_result WHERE batch_id=%s AND alert_id IS NOT NULL",
            (plan.batch_id,),
        ).fetchone()[0]
    )
    if tx_count != plan.transaction_rows or detection_count != plan.snapshot_rows or alert_count != plan.triggered_rows:
        raise RuntimeError(
            f"load counts mismatch: transactions={tx_count}, detections={detection_count}, alerts={alert_count}"
        )
    pg.execute(
        """
        UPDATE behavior_batch SET
          status='completed', completed_at=now(), failure_reason=NULL,
          transactions_inserted=%s, transactions_existing=%s,
          detections_written=%s, alerts_created=%s
        WHERE batch_id=%s
        """,
        (tx_count, plan.transaction_rows - tx_count, detection_count, alert_count, plan.batch_id),
    )
    pg.execute("ANALYZE account")
    pg.execute("ANALYZE transaction")
    pg.execute("ANALYZE behavior_feature_snapshot")
    pg.execute("ANALYZE detection_result")
    pg.execute("ANALYZE alert")
    pg.commit()
    return {"transactions": tx_count, "detections": detection_count, "alerts": alert_count}


def _canonical_load_counts(pg: psycopg.Connection[Any], plan: ReleasePlan) -> tuple[int, int, int]:
    row = pg.execute(
        """
        SELECT
          (SELECT count(*) FROM account),
          (SELECT count(*) FROM transaction WHERE behavior_batch_id=%s),
          (SELECT count(*) FROM label.label_laundering l
             JOIN transaction t USING (transaction_id) WHERE t.behavior_batch_id=%s)
        """,
        (plan.batch_id, plan.batch_id),
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def load_release(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _absolute(args.db)
    scores_path = _absolute(args.scores)
    manifest_path = _absolute(args.manifest)
    bundle_path = _absolute(args.bundle)
    print("Validating release checksums and canonical populations...", flush=True)
    plan = build_release_plan(
        db_path=db_path,
        scores_path=scores_path,
        manifest_path=manifest_path,
        bundle_path=bundle_path,
    )
    if args.dry_run:
        return {"status": "validated", "dry_run": True, "plan": asdict(plan)}

    database_url = args.database_url or get_settings().database_url
    pg = psycopg.connect(_psycopg_url(database_url))
    try:
        pg.execute("SET TIME ZONE 'UTC'")
        pg.execute("SET synchronous_commit=off")
        _require_schema(pg)
        completed = _completed_counts(pg, plan)
        if completed is not None:
            return {"status": "already_completed", "batch_id": plan.batch_id, **completed}
        _start_batch(pg, plan)

        duck = duckdb.connect(str(db_path), read_only=True)
        try:
            duck.execute("SET TimeZone='UTC'")
            duck.execute("SET threads=4")
            with tempfile.TemporaryDirectory(prefix="fin07-fusion-load-") as temp_name:
                temp_dir = Path(temp_name)
                account_count, transaction_count, label_count = _canonical_load_counts(pg, plan)
                if (
                    account_count == plan.account_rows
                    and transaction_count == plan.transaction_rows
                    and label_count == plan.transaction_rows
                ):
                    print("[1/3] Resuming: canonical accounts, transactions and labels already complete", flush=True)
                else:
                    _load_accounts(pg, duck, temp_dir)
                    _load_transactions(pg, duck, temp_dir, plan)
                _load_scores(pg, temp_dir, scores_path, plan)
        finally:
            duck.close()

        print("[5/5] Verifying counts and marking the release completed", flush=True)
        counts = _complete(pg, plan)
        return {"status": "completed", "batch_id": plan.batch_id, **counts}
    except Exception as exc:
        pg.rollback()
        try:
            pg.execute(
                """
                UPDATE behavior_batch SET status='failed', completed_at=now(), failure_reason=%s
                 WHERE batch_id=%s
                """,
                (str(exc)[:2000], plan.batch_id),
            )
            pg.commit()
        except Exception:
            pg.rollback()
        raise
    finally:
        pg.close()


def main(argv: list[str] | None = None) -> int:
    result = load_release(parse_args(argv))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
