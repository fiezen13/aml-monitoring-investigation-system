#!/usr/bin/env python3
"""Run a local Behaviour ML PoC batch from canonical CSV to PostgreSQL.

The runner is deterministic and contains no Gemini calls:

CSV -> canonical transactions -> PostgreSQL + DuckDB -> 20 features ->
Isolation Forest -> durable detection_result -> triggered ML alerts.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import joblib
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extract_features import extract_features, extract_split_features  # noqa: E402
from scripts.generate_scores import _load_artifact, score_features  # noqa: E402
from scripts.publish_if_alerts import publish_rows  # noqa: E402
from scripts.train_isolation_forest import train  # noqa: E402
from src.behavior.batch import (  # noqa: E402
    BatchValidationError,
    assign_time_splits,
    parse_batch_csv,
    source_checksum,
    write_feature_duckdb,
)
from src.behavior.repository import BehaviorBatchRepository, batch_id_for  # noqa: E402
from src.db.session import get_session  # noqa: E402
from src.services.if_alert_publish import stable_alert_id  # noqa: E402
from src.services.if_detection_result import build_detection_result  # noqa: E402

log = logging.getLogger("fin07.behavior_batch")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Canonical behavior-batch CSV")
    parser.add_argument(
        "--subject-accounts",
        type=Path,
        default=None,
        help="Manifest of accounts with complete history; only these are scored",
    )
    parser.add_argument("--window", choices=("1d", "7d"), default="7d")
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--top-k", type=int, default=100, help="Maximum triggered alerts to create")
    parser.add_argument("--typology", default="T02", help="Candidate typology T01..T10")
    parser.add_argument("--model", type=Path, default=None, help="Existing Isolation Forest joblib artifact")
    parser.add_argument(
        "--model-version",
        default=None,
        help="Required release identifier; defaults to if_behavior_poc_<window>_v1",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("data/processed/behavior-batches"),
        help="Artifact root; each batch gets an isolated subdirectory",
    )
    parser.add_argument("--max-records", type=int, default=100_000)
    parser.add_argument(
        "--allow-rejected",
        action="store_true",
        help="Continue with valid rows; default is fail-closed if any row is rejected",
    )
    return parser.parse_args(argv)


def _model_version(model_path: Path | None, requested: str | None, window: str) -> str:
    if requested:
        return requested
    if model_path is not None:
        artifact = joblib.load(model_path)
        if not isinstance(artifact, dict):
            raise ValueError("model artifact must be a dictionary")
        version = str(artifact.get("model_version") or "").strip()
        if not version:
            raise ValueError("external model artifact must contain model_version or use --model-version")
        return version
    return f"if_behavior_poc_{window}_v1"


def _latest_scores(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return scores
    return (
        scores.sort_values(["account_key", "as_of_ts"], kind="mergesort")
        .drop_duplicates(subset=["account_key"], keep="last")
        .reset_index(drop=True)
    )


def _operational_features(transactions, window: str) -> pd.DataFrame:
    frame = pl.DataFrame(
        {
            "occurred_at": [transaction.occurred_at for transaction in transactions],
            "from_account_key": [transaction.from_account_key for transaction in transactions],
            "to_account_key": [transaction.to_account_key for transaction in transactions],
            "amount": [float(transaction.amount) for transaction in transactions],
        },
        schema={
            "occurred_at": pl.Datetime(time_unit="us", time_zone="UTC"),
            "from_account_key": pl.Utf8,
            "to_account_key": pl.Utf8,
            "amount": pl.Float64,
        },
    )
    return extract_split_features(frame, window).to_pandas()


def run(args: argparse.Namespace) -> dict[str, object]:
    if not 0 <= args.threshold <= 1:
        raise ValueError("--threshold must be in [0, 1]")
    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1")
    if not re.fullmatch(r"T(0[1-9]|10)", args.typology):
        raise ValueError("--typology must be T01..T10")
    if args.model is not None and not args.model.is_file():
        raise FileNotFoundError(args.model)

    parsed = parse_batch_csv(args.input, max_records=args.max_records)
    if parsed.rejected and not args.allow_rejected:
        sample = "; ".join(f"line {item.line_number}: {item.reason}" for item in parsed.rejected[:5])
        raise BatchValidationError(
            f"{len(parsed.rejected)} row(s) rejected; batch aborted (use --allow-rejected to continue): {sample}"
        )

    model_version = _model_version(args.model, args.model_version, args.window)
    batch_id = batch_id_for(parsed.source_sha256, args.window, model_version)
    work_dir = args.work_root / batch_id
    work_dir.mkdir(parents=True, exist_ok=True)
    duckdb_path = work_dir / "transactions.duckdb"
    scores_path = work_dir / "if_scores.parquet"

    splits = assign_time_splits(parsed.transactions)
    write_feature_duckdb(duckdb_path, parsed.transactions, splits)
    extract_features(args.window, duckdb_path, work_dir)

    generated_model = work_dir / f"isolation_forest_model_{args.window}.joblib"
    if args.model is None and generated_model.exists():
        model_path = generated_model
        stored_version = str(_load_artifact(model_path).get("model_version") or "")
        if stored_version != model_version:
            raise ValueError(f"existing generated artifact version {stored_version!r} does not match {model_version!r}")
    elif args.model is None:
        model_path = train(args.window, work_dir, model_version)
    else:
        model_path = args.model
    model_sha256 = source_checksum(model_path)
    inference_features = _operational_features(parsed.transactions, args.window)
    if args.subject_accounts is not None:
        # Counterparties are present only for the rows that touch a subject, so
        # their feature vectors describe that fragment rather than the account.
        # Scoring them manufactures anomalies out of the batch's own boundary.
        subjects = {
            line.strip() for line in args.subject_accounts.read_text(encoding="utf-8").splitlines() if line.strip()
        }
        if not subjects:
            raise ValueError(f"--subject-accounts file is empty: {args.subject_accounts}")
        inference_features = inference_features[inference_features["account_key"].isin(subjects)].copy()
        if inference_features.empty:
            raise ValueError("no batch account matched --subject-accounts")
    train_reference = pd.read_parquet(work_dir / f"features_train_{args.window}.parquet")
    scores = score_features(inference_features, _load_artifact(model_path), train_reference)
    scores.to_parquet(scores_path, index=False)
    latest = _latest_scores(scores)
    triggered = latest[latest["anomaly_score"] >= args.threshold].copy()
    triggered = triggered.sort_values("anomaly_score", ascending=False, kind="mergesort").head(args.top_k)

    rows_read = len(parsed.transactions) + len(parsed.rejected)
    try:
        with get_session() as session:
            repository = BehaviorBatchRepository(session)
            repository.require_schema()
            repository.start_batch(
                batch_id=batch_id,
                source_name=args.input.name,
                source_sha256=parsed.source_sha256,
                window=args.window,
                model_version=model_version,
                model_sha256=model_sha256,
                threshold=args.threshold,
                rows_read=rows_read,
                rows_rejected=len(parsed.rejected),
            )
            ingest_stats = repository.ingest_transactions(
                batch_id=batch_id,
                source_name=args.input.name,
                transactions=parsed.transactions,
                splits=splits,
            )
            detection_stats = repository.persist_latest_results(
                batch_id=batch_id,
                scores=latest,
                threshold=args.threshold,
                typology_code=args.typology,
            )
            alert_stats = publish_rows(session, triggered, args.typology, dry_run=False)

            result_links: list[tuple[str, str]] = []
            for record in triggered.to_dict(orient="records"):
                result_id = build_detection_result(
                    record,
                    threshold=args.threshold,
                    typology_code=args.typology,
                )["result_id"]
                alert_id = stable_alert_id(
                    str(record["account_key"]),
                    record["as_of_ts"],
                    str(record["window"]),
                    str(record["model_version"]),
                )
                result_links.append((result_id, alert_id))
            repository.link_alerts(result_links)

            completion = {
                "transactions_inserted": ingest_stats["transactions_inserted"],
                "transactions_existing": ingest_stats["transactions_existing"],
                "detections_written": detection_stats["detections_written"],
                "alerts_created": alert_stats["inserted"],
            }
            repository.complete_batch(batch_id, completion)
    except Exception as exc:
        # The main transaction rolls back on failure. Record a compact failed
        # run in a fresh transaction when the migration itself is available.
        try:
            with get_session() as session:
                repository = BehaviorBatchRepository(session)
                repository.require_schema()
                repository.start_batch(
                    batch_id=batch_id,
                    source_name=args.input.name,
                    source_sha256=parsed.source_sha256,
                    window=args.window,
                    model_version=model_version,
                    model_sha256=model_sha256,
                    threshold=args.threshold,
                    rows_read=rows_read,
                    rows_rejected=len(parsed.rejected),
                )
                repository.fail_batch(batch_id, f"{type(exc).__name__}: {exc}")
        except Exception:
            log.exception("Could not persist failed batch metadata")
        raise

    return {
        "batch_id": batch_id,
        "source": args.input.name,
        "source_sha256": parsed.source_sha256,
        "rows_read": rows_read,
        "rows_rejected": len(parsed.rejected),
        **ingest_stats,
        **detection_stats,
        "alerts_created": alert_stats["inserted"],
        "alerts_existing": alert_stats["skipped"],
        "work_dir": str(work_dir),
        "model": str(model_path),
        "model_sha256": model_sha256,
        "graph_used": False,
        "fusion_used": False,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = run(parse_args(argv))
    except Exception as exc:
        log.error("Behaviour batch failed: %s", exc)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
