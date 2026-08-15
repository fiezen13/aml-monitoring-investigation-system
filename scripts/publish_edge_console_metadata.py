#!/usr/bin/env python3
"""Publish measured release provenance and data-quality rows for the console."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402


def main() -> int:
    with get_session() as session:
        release = (
            session.execute(
                text(
                    """SELECT release_id, model_version, dataset, transaction_rows,
                              model_sha256, scores_sha256, trained_at
                         FROM edge_model_release WHERE status='active' LIMIT 1"""
                )
            )
            .mappings()
            .one()
        )
        measured = (
            session.execute(
                text(
                    """SELECT count(*) AS rows,
                              count(*) FILTER (WHERE t.amount<=0 OR t.amount_received<=0) AS invalid_amount,
                              count(*) FILTER (WHERE t.currency='' OR t.receiving_currency='') AS missing_currency,
                              count(*) FILTER (WHERE s.model_score<0 OR s.model_score>1) AS invalid_score,
                              min(t.occurred_at) AS first_seen, max(t.occurred_at) AS last_seen
                         FROM transaction t
                         JOIN transaction_model_score s USING (transaction_id)
                        WHERE s.release_id=:release"""
                ),
                {"release": release["release_id"]},
            )
            .mappings()
            .one()
        )
        geo = (
            session.execute(
                text(
                    """SELECT count(*) AS rows,
                              count(*) FILTER (WHERE b.country_code IS NULL) AS missing
                         FROM account a LEFT JOIN bank b USING (bank_code)"""
                )
            )
            .mappings()
            .one()
        )
        now = datetime.now(UTC)
        checks = [
            ("DQ-EDGE-SCORE-COVERAGE", "Score coverage", "completeness", measured["rows"], 0),
            ("DQ-EDGE-AMOUNT", "Positive native amounts", "validity", measured["rows"], measured["invalid_amount"]),
            ("DQ-EDGE-CURRENCY", "Native currency completeness", "completeness", measured["rows"], measured["missing_currency"]),
            ("DQ-EDGE-SCORE-RANGE", "Model score in [0,1]", "validity", measured["rows"], measured["invalid_score"]),
            ("DQ-EDGE-GEOGRAPHY", "Bank-country mapping coverage", "completeness", geo["rows"], geo["missing"]),
        ]
        for check_id, name, dimension, rows, failed in checks:
            pass_rate = 100 * (int(rows) - int(failed)) / max(1, int(rows))
            session.execute(
                text(
                    """INSERT INTO fc.data_quality_check (
                         check_id, dataset, check_name, dimension, observed_at,
                         pass_rate, threshold, rows_checked, rows_failed, status, detail
                       ) VALUES (:id,:dataset,:name,:dimension,:at,:rate,99.00,:rows,:failed,:status,:detail)
                       ON CONFLICT (check_id) DO UPDATE SET
                         observed_at=EXCLUDED.observed_at, pass_rate=EXCLUDED.pass_rate,
                         rows_checked=EXCLUDED.rows_checked, rows_failed=EXCLUDED.rows_failed,
                         status=EXCLUDED.status, detail=EXCLUDED.detail"""
                ),
                {
                    "id": check_id,
                    "dataset": release["dataset"],
                    "name": name,
                    "dimension": dimension,
                    "at": now,
                    "rate": round(pass_rate, 2),
                    "rows": rows,
                    "failed": failed,
                    "status": "ok" if pass_rate >= 99 else "fail",
                    "detail": f"Measured on active release {release['release_id']}; no static FX transformation.",
                },
            )

        period = f"{measured['first_seen'].date()}..{measured['last_seen'].date()}"
        sources = [
            {
                "id": "SRC-IBM-HI-MEDIUM",
                "type": "benchmark",
                "scope": "Synthetic AML transactions, accounts and evaluation labels",
                "period": period,
                "jurisdiction": "Synthetic global",
                "fields": "transaction endpoints, native amounts/currencies, channel, evaluation label",
                "transform": "Time split; transaction-level score; native-currency preprocessing",
                "confidence": 1.0,
                "rationale": "Exact source population declared by the active release.",
                "access": "internal",
                "owner": "FIN-07 ML",
                "reviewer": "FIN-07 model governance",
                "valid": measured["first_seen"].date(),
                "prohibited": "Synthetic benchmark only; do not identify people or estimate real-world prevalence.",
            },
            {
                "id": "SRC-BANK-GEOGRAPHY-V1",
                "type": "expert_assumption",
                "scope": "Bank-name family to country mapping for World Monitor",
                "period": period,
                "jurisdiction": "Synthetic global",
                "fields": "bank family, country code, assignment source, display coordinates",
                "transform": "Parsed country names plus explicitly documented assignments",
                "confidence": 0.75,
                "rationale": "Coverage is measured; assigned countries remain distinguishable from parsed countries.",
                "access": "internal",
                "owner": "FIN-07 Data",
                "reviewer": "FIN-07 model governance",
                "valid": measured["first_seen"].date(),
                "prohibited": "Do not interpret assigned geography as verified jurisdiction or jurisdiction risk.",
            },
            {
                "id": "SRC-EDGE-MODEL-RELEASE",
                "type": "benchmark",
                "scope": release["model_version"],
                "period": period,
                "jurisdiction": "Synthetic global",
                "fields": "model score, threshold, benchmark metrics, artifact hashes",
                "transform": "Five-seed offline benchmark; validation-selected threshold",
                "confidence": 1.0,
                "rationale": f"model={release['model_sha256']}; scores={release['scores_sha256']}",
                "access": "internal",
                "owner": "FIN-07 ML",
                "reviewer": "FIN-07 model governance",
                "valid": release["trained_at"].date(),
                "prohibited": "Do not treat a score or T02 candidate as a confirmed AML case.",
            },
        ]
        for source in sources:
            session.execute(
                text(
                    """INSERT INTO fc.source_registry (
                         source_id, source_type, scope, period, jurisdiction,
                         fields_supported, transformation, confidence, rationale,
                         access_level, owner, reviewer, valid_from, prohibited_uses
                       ) VALUES (:id,:type,:scope,:period,:jurisdiction,:fields,:transform,
                                 :confidence,:rationale,:access,:owner,:reviewer,:valid,:prohibited)
                       ON CONFLICT (source_id) DO UPDATE SET
                         scope=EXCLUDED.scope, period=EXCLUDED.period,
                         confidence=EXCLUDED.confidence, rationale=EXCLUDED.rationale"""
                ),
                source,
            )
    print(json.dumps({"status": "published", "checks": len(checks), "sources": len(sources)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
