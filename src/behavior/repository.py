"""PostgreSQL persistence for the deterministic Behaviour batch pipeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.behavior.batch import BatchTransaction
from src.services.if_detection_result import build_detection_result

FEATURE_DEFINITION_VERSION = "feature_spec_v1"


def batch_id_for(source_sha256: str, window: str, model_version: str) -> str:
    raw = f"{source_sha256}|{window}|{model_version}"
    return f"BAT-BEH-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def snapshot_id_for(account_key: str, as_of_time: Any, window: str, model_version: str) -> str:
    raw = f"{account_key}|{as_of_time}|{window}|{FEATURE_DEFINITION_VERSION}|{model_version}"
    return f"BFS-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


class BehaviorBatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_schema(self) -> None:
        exists = self.session.execute(
            text(
                """SELECT to_regclass('public.detection_result') IS NOT NULL
                          AND EXISTS (
                              SELECT 1 FROM information_schema.columns
                               WHERE table_schema = 'public'
                                 AND table_name = 'behavior_batch'
                                 AND column_name = 'model_sha256'
                          )"""
            )
        ).scalar_one()
        if not exists:
            raise RuntimeError("Behaviour batch schema is missing; run `make migrate` first")

    def start_batch(
        self,
        *,
        batch_id: str,
        source_name: str,
        source_sha256: str,
        window: str,
        model_version: str,
        model_sha256: str,
        threshold: float,
        rows_read: int,
        rows_rejected: int,
    ) -> None:
        existing = (
            self.session.execute(
                text("SELECT threshold, model_sha256 FROM behavior_batch WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            if abs(float(existing["threshold"]) - float(threshold)) > 1e-9:
                raise ValueError(
                    "A batch with this source/model already exists at a different threshold; "
                    "use a new --model-version so the detector release remains auditable"
                )
            if existing["model_sha256"] and existing["model_sha256"] != model_sha256:
                raise ValueError(
                    "The same model_version points to different artifact bytes; publish a new --model-version"
                )
        self.session.execute(
            text(
                """INSERT INTO behavior_batch (
                       batch_id, source_name, source_sha256, status, feature_window,
                       model_version, model_sha256, threshold, rows_read, rows_rejected
                   ) VALUES (
                       :batch_id, :source_name, :source_sha256, 'running', :window,
                       :model_version, :model_sha256, :threshold, :rows_read, :rows_rejected
                   )
                   ON CONFLICT (batch_id) DO UPDATE SET
                       status = 'running',
                       rows_read = EXCLUDED.rows_read, rows_rejected = EXCLUDED.rows_rejected,
                       completed_at = NULL, failure_reason = NULL"""
            ),
            {
                "batch_id": batch_id,
                "source_name": source_name,
                "source_sha256": source_sha256,
                "window": window,
                "model_version": model_version,
                "model_sha256": model_sha256,
                "threshold": threshold,
                "rows_read": rows_read,
                "rows_rejected": rows_rejected,
            },
        )

    def ingest_transactions(
        self,
        *,
        batch_id: str,
        source_name: str,
        transactions: list[BatchTransaction],
        splits: dict[str, str],
    ) -> dict[str, int]:
        accounts: dict[str, tuple[str, str]] = {}
        for transaction in transactions:
            accounts[transaction.from_account_key] = (transaction.from_bank, transaction.from_account)
            accounts[transaction.to_account_key] = (transaction.to_bank, transaction.to_account)

        for account_key, (bank_code, account_number) in accounts.items():
            self._ensure_subject(account_key, bank_code, account_number, transactions)

        before = int(
            self.session.execute(
                text("SELECT count(*) FROM transaction WHERE source_transaction_id = ANY(:ids)"),
                {"ids": [transaction.source_transaction_id for transaction in transactions]},
            ).scalar_one()
        )

        params = []
        now = datetime.now(tz=UTC)
        for transaction in transactions:
            split = splits[transaction.source_transaction_id]
            params.append(
                {
                    "occurred_at": transaction.occurred_at,
                    "from_account_key": transaction.from_account_key,
                    "to_account_key": transaction.to_account_key,
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "amount_received": transaction.amount_received,
                    "receiving_currency": transaction.receiving_currency,
                    "channel": transaction.channel,
                    "remarks": transaction.remarks,
                    "dataset_split": "validation" if split == "val" else split,
                    "source_transaction_id": transaction.source_transaction_id,
                    "source_dataset": "behavior-batch-v1",
                    "source_file": source_name,
                    "source_line_number": transaction.source_line_number,
                    "ingested_at": now,
                    "batch_id": batch_id,
                }
            )
        self.session.execute(
            text(
                """INSERT INTO transaction (
                       occurred_at, from_account_key, to_account_key, amount, currency,
                       amount_received, receiving_currency, channel, remarks, dataset_split,
                       source_transaction_id, source_dataset, source_file, source_line_number,
                       ingested_at, behavior_batch_id
                   ) VALUES (
                       :occurred_at, :from_account_key, :to_account_key, :amount, :currency,
                       :amount_received, :receiving_currency, :channel, :remarks, :dataset_split,
                       :source_transaction_id, :source_dataset, :source_file, :source_line_number,
                       :ingested_at, :batch_id
                   ) ON CONFLICT DO NOTHING"""
            ),
            params,
        )

        after = int(
            self.session.execute(
                text("SELECT count(*) FROM transaction WHERE source_transaction_id = ANY(:ids)"),
                {"ids": [transaction.source_transaction_id for transaction in transactions]},
            ).scalar_one()
        )
        inserted = max(0, after - before)
        return {
            "transactions_inserted": inserted,
            "transactions_existing": len(transactions) - inserted,
            "subjects_seen": len(accounts),
        }

    def _ensure_subject(
        self,
        account_key: str,
        bank_code: str,
        account_number: str,
        transactions: list[BatchTransaction],
    ) -> None:
        if self.session.execute(
            text("SELECT 1 FROM account WHERE account_key = :key"), {"key": account_key}
        ).scalar_one_or_none():
            return

        customer_id = f"CUST-BATCH-{hashlib.sha1(account_key.encode('utf-8')).hexdigest()[:12]}"
        first_seen = min(
            transaction.occurred_at.date()
            for transaction in transactions
            if account_key in {transaction.from_account_key, transaction.to_account_key}
        )
        self.session.execute(
            text(
                """INSERT INTO customer (
                       customer_id, customer_type, prototype, occupation,
                       declared_income_band, expected_monthly_volume,
                       registered_country, onboarding_date, risk_rating
                   ) VALUES (
                       :customer_id, 'organisation', 'enterprise', :occupation,
                       'kyc_unavailable', 0, 'XX', :onboarding_date, 'medium'
                   ) ON CONFLICT (customer_id) DO NOTHING"""
            ),
            {
                "customer_id": customer_id,
                "occupation": "KYC unavailable — Behaviour batch import",
                "onboarding_date": first_seen,
            },
        )
        self.session.execute(
            text(
                """INSERT INTO account (
                       account_key, customer_id, bank_code, account_number, opened_at, status
                   ) VALUES (:key, :customer_id, :bank, :number, :opened_at, 'active')
                   ON CONFLICT (account_key) DO NOTHING"""
            ),
            {
                "key": account_key,
                "customer_id": customer_id,
                "bank": bank_code,
                "number": account_number,
                "opened_at": first_seen,
            },
        )

    def persist_latest_results(
        self,
        *,
        batch_id: str,
        scores: pd.DataFrame,
        threshold: float,
        typology_code: str,
    ) -> dict[str, int]:
        if scores.empty:
            return {"detections_written": 0, "triggered": 0}

        ordered = scores.sort_values(["account_key", "as_of_ts"], kind="mergesort")
        latest = ordered.drop_duplicates(subset=["account_key"], keep="last")
        detections_written = 0
        triggered = 0
        evaluated_at = datetime.now(tz=UTC)

        for record in latest.to_dict(orient="records"):
            payload = build_detection_result(
                record,
                threshold=threshold,
                typology_code=typology_code,
                evaluated_at=evaluated_at,
            )
            model_version = payload["detector"]["version"]
            snapshot_id = snapshot_id_for(
                str(record["account_key"]), record["as_of_ts"], str(record["window"]), model_version
            )
            feature_names = [
                key
                for key in record
                if key
                not in {
                    "account_key",
                    "as_of_ts",
                    "window",
                    "anomaly_score",
                    "model_version",
                    "top_anomalous_features",
                }
            ]
            features = {key: _json_number(record[key]) for key in feature_names}
            self.session.execute(
                text(
                    """INSERT INTO behavior_feature_snapshot (
                           snapshot_id, batch_id, account_key, as_of_time, feature_window,
                           definition_version, model_version, features
                       ) VALUES (
                           :snapshot_id, :batch_id, :account_key, :as_of_time, :window,
                           :definition_version, :model_version, CAST(:features AS jsonb)
                       ) ON CONFLICT (snapshot_id) DO NOTHING"""
                ),
                {
                    "snapshot_id": snapshot_id,
                    "batch_id": batch_id,
                    "account_key": record["account_key"],
                    "as_of_time": record["as_of_ts"],
                    "window": record["window"],
                    "definition_version": FEATURE_DEFINITION_VERSION,
                    "model_version": model_version,
                    "features": json.dumps(features, ensure_ascii=False),
                },
            )
            result = self.session.execute(
                text(
                    """INSERT INTO detection_result (
                           result_id, batch_id, snapshot_id, account_key, detector_id,
                           detector_type, detector_version, evaluated_at, as_of_time,
                           score, confidence, triggered, threshold, reason_codes,
                           typology_candidates, feature_refs, payload
                       ) VALUES (
                           :result_id, :batch_id, :snapshot_id, :account_key, :detector_id,
                           :detector_type, :detector_version, :evaluated_at, :as_of_time,
                           :score, :confidence, :triggered, :threshold,
                           CAST(:reason_codes AS jsonb), CAST(:typologies AS jsonb),
                           CAST(:feature_refs AS jsonb), CAST(:payload AS jsonb)
                       ) ON CONFLICT (result_id) DO NOTHING
                       RETURNING result_id"""
                ),
                {
                    "result_id": payload["result_id"],
                    "batch_id": batch_id,
                    "snapshot_id": snapshot_id,
                    "account_key": payload["entity"]["entity_id"],
                    "detector_id": payload["detector"]["detector_id"],
                    "detector_type": payload["detector"]["detector_type"],
                    "detector_version": model_version,
                    "evaluated_at": payload["evaluated_at"],
                    "as_of_time": payload["as_of_time"],
                    "score": payload["score"],
                    "confidence": payload["confidence"],
                    "triggered": payload["triggered"],
                    "threshold": payload["threshold"],
                    "reason_codes": json.dumps(payload["reason_codes"], ensure_ascii=False),
                    "typologies": json.dumps(payload["typology_candidates"], ensure_ascii=False),
                    "feature_refs": json.dumps(payload["feature_refs"], ensure_ascii=False),
                    "payload": json.dumps(payload, ensure_ascii=False),
                },
            ).scalar_one_or_none()
            detections_written += int(result is not None)
            triggered += int(payload["triggered"])
        return {"detections_written": detections_written, "triggered": triggered}

    def link_alerts(self, result_to_alert: Iterable[tuple[str, str]]) -> None:
        for result_id, alert_id in result_to_alert:
            self.session.execute(
                text("UPDATE detection_result SET alert_id = :alert_id WHERE result_id = :result_id"),
                {"result_id": result_id, "alert_id": alert_id},
            )

    def complete_batch(self, batch_id: str, stats: dict[str, int]) -> None:
        self.session.execute(
            text(
                """UPDATE behavior_batch SET
                       status = 'completed', completed_at = now(),
                       transactions_inserted = :transactions_inserted,
                       transactions_existing = :transactions_existing,
                       detections_written = :detections_written,
                       alerts_created = :alerts_created,
                       failure_reason = NULL
                   WHERE batch_id = :batch_id"""
            ),
            {"batch_id": batch_id, **stats},
        )

    def fail_batch(self, batch_id: str, reason: str) -> None:
        self.session.execute(
            text(
                """UPDATE behavior_batch SET status = 'failed', completed_at = now(),
                       failure_reason = :reason WHERE batch_id = :batch_id"""
            ),
            {"batch_id": batch_id, "reason": reason[:2000]},
        )


def _json_number(value: Any) -> int | float | str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (int, float, str)):
        return value
    return float(value)
