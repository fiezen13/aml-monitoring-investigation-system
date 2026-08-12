"""Publish Isolation Forest (ml) alerts into Postgres for Alert Center.

Dùng chung bởi ``scripts/publish_if_alerts.py`` và ``POST /api/v1/internal/alerts``.

Mọi ghi DB đi qua ``get_session()`` (commit khi thành công, rollback khi lỗi) —
alert + alert_reason nằm trong cùng một transaction, tránh alert thiếu reasons (NT7).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

ML_WEIGHT = 0.35
MIN_REASONS = 3
DEFAULT_TYPOLOGY = "T02"


def stable_alert_id(account_key: str, as_of_ts: Any, window: str, model_version: str) -> str:
    raw = f"{account_key}|{as_of_ts}|{window}|{model_version}|ml"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"ALT-IF-{digest}"


def split_account_key(account_key: str) -> tuple[str, str]:
    if ":" not in account_key:
        raise ValueError(f"account_key khong dung format bank:account — {account_key!r}")
    bank_code, account_number = account_key.split(":", 1)
    if not bank_code or not account_number:
        raise ValueError(f"account_key rong sau khi tach — {account_key!r}")
    return bank_code, account_number


def customer_id_for(account_key: str) -> str:
    digest = hashlib.sha1(account_key.encode("utf-8")).hexdigest()[:12]
    return f"CUST-IF-{digest}"


def ensure_subject(session: Session, account_key: str, as_of_ts: Any) -> bool:
    """Tao customer + account toi thieu. True neu vua tao account.

    Moi gia tri dong deu qua bind parameters (khong noi chuoi SQL).
    """
    exists = session.execute(
        text("SELECT 1 FROM account WHERE account_key = :k"),
        {"k": account_key},
    ).scalar_one_or_none()
    if exists:
        return False

    bank_code, account_number = split_account_key(account_key)
    customer_id = customer_id_for(account_key)

    if isinstance(as_of_ts, datetime):
        opened = as_of_ts.date()
    elif isinstance(as_of_ts, date):
        opened = as_of_ts
    else:
        opened = datetime.now(tz=UTC).date()

    cust_exists = session.execute(
        text("SELECT 1 FROM customer WHERE customer_id = :c"),
        {"c": customer_id},
    ).scalar_one_or_none()
    if not cust_exists:
        session.execute(
            text(
                """
                INSERT INTO customer (
                    customer_id, customer_type, prototype, occupation, declared_income_band,
                    expected_monthly_volume, registered_country, onboarding_date, risk_rating
                ) VALUES (
                    :customer_id, :customer_type, :prototype, :occupation, :declared_income_band,
                    :expected_monthly_volume, :registered_country, :onboarding_date, :risk_rating
                )
                """
            ),
            {
                "customer_id": customer_id,
                "customer_type": "individual",
                "prototype": "salaried",
                "occupation": "IF subject (synthetic)",
                "declared_income_band": "unknown",
                "expected_monthly_volume": 0,
                "registered_country": "XX",
                "onboarding_date": opened,
                "risk_rating": "medium",
            },
        )

    session.execute(
        text(
            """
            INSERT INTO account (
                account_key, customer_id, bank_code, account_number, opened_at, status
            ) VALUES (
                :account_key, :customer_id, :bank_code, :account_number, :opened_at, :status
            )
            """
        ),
        {
            "account_key": account_key,
            "customer_id": customer_id,
            "bank_code": bank_code,
            "account_number": account_number,
            "opened_at": opened,
            "status": "active",
        },
    )
    return True


def validate_typology(typology_code: str) -> None:
    if not re.fullmatch(r"T(0[1-9]|10)", typology_code):
        raise ValueError(f"typology_code khong hop le: {typology_code}")


def _clean_reasons(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chuan hoa + khu trung factor_code; raise neu < MIN_REASONS (truoc khi INSERT)."""
    if len(reasons) < MIN_REASONS:
        raise ValueError(f"NT7: can >= {MIN_REASONS} reasons, nhan {len(reasons)}")

    seen_codes: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for reason in reasons:
        code = str(reason["factor_code"])[:64]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        cleaned.append(
            {
                "factor_code": code,
                "factor_label": str(reason["factor_label"])[:500],
                "contribution": round(float(reason["contribution"]), 2),
                "weight": round(float(reason.get("weight", ML_WEIGHT)), 2),
            }
        )
    if len(cleaned) < MIN_REASONS:
        raise ValueError(f"NT7: sau khi khu trung factor_code con {len(cleaned)} reasons")
    return cleaned


def insert_ml_alert(
    session: Session,
    *,
    alert_id: str,
    account_key: str,
    risk_score: float,
    typology_code: str,
    reasons: list[dict[str, Any]],
    as_of_ts: Any | None = None,
) -> dict[str, Any]:
    """Insert alert detector=ml + alert_reason. Idempotent theo alert_id.

    ``reasons`` moi phan tu can: factor_code, factor_label, contribution, weight.

    Goi trong ``with get_session()``: neu bat ky INSERT nao fail, ca transaction
    bi rollback (khong de alert ton tai ma thieu alert_reason).
    """
    validate_typology(typology_code)
    cleaned = _clean_reasons(reasons)
    risk = round(min(max(float(risk_score), 0.0), 100.0), 2)

    subjects_created = ensure_subject(
        session, account_key, as_of_ts or datetime.now(tz=UTC)
    )

    existing = session.execute(
        text("SELECT 1 FROM alert WHERE alert_id = :a"),
        {"a": alert_id},
    ).scalar_one_or_none()
    if existing:
        return {
            "alert_id": alert_id,
            "created": False,
            "subjects_created": subjects_created,
        }

    created_at = datetime.now(tz=UTC)
    session.execute(
        text(
            """
            INSERT INTO alert (
                alert_id, account_key, transaction_id, typology_code, detector,
                risk_score, status, case_id, created_at
            ) VALUES (
                :alert_id, :account_key, NULL, :typology_code, 'ml',
                :risk_score, 'open', NULL, :created_at
            )
            """
        ),
        {
            "alert_id": alert_id,
            "account_key": account_key,
            "typology_code": typology_code,
            "risk_score": risk,
            "created_at": created_at,
        },
    )
    for reason in cleaned:
        session.execute(
            text(
                """
                INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
                VALUES (:alert_id, :factor_code, :factor_label, :contribution, :weight)
                """
            ),
            {"alert_id": alert_id, **reason},
        )

    return {
        "alert_id": alert_id,
        "created": True,
        "subjects_created": subjects_created,
        "risk_score": risk,
        "factor_count": len(cleaned),
    }
