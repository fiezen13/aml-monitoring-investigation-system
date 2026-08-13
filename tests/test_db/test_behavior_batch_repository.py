from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.train_isolation_forest import FEATURE_COLS
from src.behavior.batch import assign_time_splits, parse_batch_csv
from src.behavior.repository import BehaviorBatchRepository, batch_id_for

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "contracts/ingestion/examples/behavior-batch-valid.csv"


@pytest.mark.integration
def test_repository_ingest_and_detection_are_idempotent(db_engine) -> None:
    parsed = parse_batch_csv(EXAMPLE)
    splits = assign_time_splits(parsed.transactions)
    model_version = "if_behavior_repository_test_v1"
    batch_id = batch_id_for(parsed.source_sha256, "7d", model_version)

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        repository = BehaviorBatchRepository(session)
        repository.require_schema()
        repository.start_batch(
            batch_id=batch_id,
            source_name=EXAMPLE.name,
            source_sha256=parsed.source_sha256,
            window="7d",
            model_version=model_version,
            model_sha256="a" * 64,
            threshold=0.7,
            rows_read=len(parsed.transactions),
            rows_rejected=0,
        )
        with pytest.raises(ValueError, match="different threshold"):
            repository.start_batch(
                batch_id=batch_id,
                source_name=EXAMPLE.name,
                source_sha256=parsed.source_sha256,
                window="7d",
                model_version=model_version,
                model_sha256="a" * 64,
                threshold=0.8,
                rows_read=len(parsed.transactions),
                rows_rejected=0,
            )
        with pytest.raises(ValueError, match="different artifact bytes"):
            repository.start_batch(
                batch_id=batch_id,
                source_name=EXAMPLE.name,
                source_sha256=parsed.source_sha256,
                window="7d",
                model_version=model_version,
                model_sha256="b" * 64,
                threshold=0.7,
                rows_read=len(parsed.transactions),
                rows_rejected=0,
            )
        first = repository.ingest_transactions(
            batch_id=batch_id,
            source_name=EXAMPLE.name,
            transactions=parsed.transactions,
            splits=splits,
        )
        second = repository.ingest_transactions(
            batch_id=batch_id,
            source_name=EXAMPLE.name,
            transactions=parsed.transactions,
            splits=splits,
        )

        assert first["transactions_inserted"] == len(parsed.transactions)
        assert second["transactions_inserted"] == 0
        assert second["transactions_existing"] == len(parsed.transactions)

        account_key = parsed.transactions[0].from_account_key
        score_row = {
            "account_key": account_key,
            "as_of_ts": parsed.transactions[-1].occurred_at,
            "window": "7d",
            **{feature: 1.0 for feature in FEATURE_COLS},
            "anomaly_score": 0.91,
            "model_version": model_version,
            "top_anomalous_features": "[]",
        }
        scores = pd.DataFrame([score_row])
        detection = repository.persist_latest_results(
            batch_id=batch_id,
            scores=scores,
            threshold=0.7,
            typology_code="T02",
        )
        duplicate = repository.persist_latest_results(
            batch_id=batch_id,
            scores=scores,
            threshold=0.7,
            typology_code="T02",
        )

        assert detection == {"detections_written": 1, "triggered": 1}
        assert duplicate == {"detections_written": 0, "triggered": 1}
        assert (
            session.execute(
                text("SELECT count(*) FROM detection_result WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            ).scalar_one()
            == 1
        )
    finally:
        session.close()
        transaction.rollback()
        connection.close()
