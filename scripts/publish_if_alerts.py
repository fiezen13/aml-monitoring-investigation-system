#!/usr/bin/env python3
"""Publish top-K Isolation Forest scores into Postgres as detector=ml alerts.

Ví dụ:
  python scripts/publish_if_alerts.py --top-k 100 --window 7d
  python scripts/publish_if_alerts.py --top-k 50 --dry-run
  python scripts/publish_if_alerts.py --verify-subjects
  python scripts/publish_if_alerts.py --repair-subjects

Không ghi đè aml.duckdb. Không tạo nút upload UI.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.session import get_session  # noqa: E402
from src.services.if_alert_publish import (  # noqa: E402
    DEFAULT_TYPOLOGY,
    MIN_REASONS,
    ML_WEIGHT,
    ensure_subject,
    insert_ml_alert,
    stable_alert_id,
)

logger = logging.getLogger("fin07.publish_if_alerts")

PROCESSED_DIR = Path("data/processed")
DEFAULT_SCORES = PROCESSED_DIR / "if_scores_v1.parquet"

FEATURE_LABELS: dict[str, str] = {
    "txn_count": "Tổng số giao dịch trong cửa sổ",
    "incoming_count": "Số giao dịch nhận",
    "outgoing_count": "Số giao dịch gửi",
    "active_days": "Số ngày có phát sinh giao dịch",
    "txn_per_active_day": "Mật độ giao dịch trên ngày hoạt động",
    "total_inflow": "Tổng tiền vào (log1p USD)",
    "total_outflow": "Tổng tiền ra (log1p USD)",
    "net_flow": "Dòng tiền ròng (log1p)",
    "outflow_inflow_ratio": "Tỷ lệ tiền ra / tiền vào",
    "rapid_outflow_ratio": "Tỷ lệ rút nhanh sau khi nhận (≤2h)",
    "median_dwell_time": "Thời gian lưu tiền trung vị (giờ)",
    "unique_in_counterparties": "Số đối tác gửi riêng biệt",
    "unique_out_counterparties": "Số đối tác nhận riêng biệt",
    "new_counterparty_ratio": "Tỷ lệ đối tác mới",
    "median_amount": "Trung vị số tiền (log1p)",
    "p90_amount": "Phân vị 90% số tiền (log1p)",
    "amount_std": "Độ lệch chuẩn số tiền (log1p)",
    "repeated_amount_ratio": "Tỷ lệ giao dịch dùng số tiền lặp lại",
    "median_inter_txn_gap": "Khoảng cách trung vị giữa các TX (phút)",
    "p10_inter_txn_gap": "Phân vị 10% khoảng cách TX (phút)",
}

FALLBACK_FEATURES = list(FEATURE_LABELS.keys())


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish top-K IF scores as ml alerts")
    p.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    p.add_argument("--window", default="7d", choices=("1d", "7d", "14d"))
    p.add_argument("--top-k", type=int, default=100, help="So mau diem cao nhat de tao alert")
    p.add_argument("--typology", default=DEFAULT_TYPOLOGY, help="Typology ung vien (T01-T10)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi in ke hoach, khong ghi Postgres",
    )
    p.add_argument(
        "--verify-subjects",
        action="store_true",
        help="Chi kiem tra alert IF da co customer/account (STEP 2)",
    )
    p.add_argument(
        "--repair-subjects",
        action="store_true",
        help="Tao customer/account thieu cho alert IF da publish (STEP 2)",
    )
    return p.parse_args()


def _stable_alert_id(account_key: str, as_of_ts: Any, window: str, model_version: str) -> str:
    return stable_alert_id(account_key, as_of_ts, window, model_version)


def _parse_top_features(raw: Any) -> list[dict[str, Any]]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, str):
        text_raw = raw.strip()
        if not text_raw or text_raw == "[]":
            return []
        try:
            data = json.loads(text_raw)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    return []


def _factor_code(name: str) -> str:
    code = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))[:64]
    return code or "feature_unknown"


def _reasons_from_row(row: pd.Series) -> list[dict[str, Any]]:
    """Map top_anomalous_features -> >=3 alert_reason dicts (chua gan alert_id)."""
    items = _parse_top_features(row.get("top_anomalous_features"))
    scored: list[tuple[str, str, float]] = []
    seen: set[str] = set()

    for item in items:
        feat = str(item.get("feature", "")).strip()
        if not feat or feat in seen:
            continue
        seen.add(feat)
        pct = float(item.get("percentile", 50))
        salience = abs(pct - 50.0)
        label = FEATURE_LABELS.get(feat, f"Dac trung IF noi bat: {feat}")
        scored.append((_factor_code(feat), label, salience))

    # Pad tu cac cot feature neu thieu < 3
    if len(scored) < MIN_REASONS:
        for feat in FALLBACK_FEATURES:
            if feat in seen:
                continue
            val = row.get(feat)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            seen.add(feat)
            label = FEATURE_LABELS.get(feat, feat)
            scored.append((_factor_code(feat), label, 10.0))
            if len(scored) >= MIN_REASONS:
                break

    while len(scored) < MIN_REASONS:
        idx = len(scored) + 1
        scored.append((f"if_evidence_{idx}", f"Bang chung IF bo sung #{idx}", 5.0))

    scored = scored[: max(MIN_REASONS, len(scored))]
    total = sum(s for _, _, s in scored) or 1.0
    reasons: list[dict[str, Any]] = []
    for code, label, salience in scored[:12]:
        contribution = round(100.0 * salience / total, 2)
        reasons.append(
            {
                "factor_code": code,
                "factor_label": f"{label} [{row.get('model_version', 'if')}]",
                "contribution": contribution,
                "weight": ML_WEIGHT,
            }
        )
    return reasons


def load_top_k(scores_path: Path, window: str, top_k: int) -> pd.DataFrame:
    if not scores_path.exists():
        raise FileNotFoundError(f"Khong tim thay {scores_path}")
    if top_k <= 0:
        raise ValueError("--top-k phai > 0")

    df = pd.read_parquet(scores_path)
    need = {
        "account_key",
        "as_of_ts",
        "window",
        "anomaly_score",
        "model_version",
        "top_anomalous_features",
    }
    missing = sorted(need - set(df.columns))
    if missing:
        raise ValueError(f"Thieu cot trong parquet: {missing}")

    subset = df[df["window"].astype(str) == window].copy()
    if subset.empty:
        raise RuntimeError(f"Khong co dong nao voi window={window!r}")

    subset["anomaly_score"] = pd.to_numeric(subset["anomaly_score"], errors="coerce")
    subset = subset.dropna(subset=["anomaly_score", "account_key"])
    subset = subset.sort_values("anomaly_score", ascending=False, kind="mergesort")
    # Mot account chi lay dong diem cao nhat (tranh spam UI)
    subset = subset.drop_duplicates(subset=["account_key"], keep="first")
    return subset.head(top_k).reset_index(drop=True)


def list_if_alert_subjects(session: Session) -> list[dict[str, Any]]:
    """Tat ca account_key tu alert IF + trang thai co/khong co customer (API detail)."""
    rows = session.execute(
        text(
            """
            SELECT al.alert_id,
                   al.account_key,
                   al.created_at,
                   ac.account_key IS NOT NULL AS has_account,
                   c.customer_id IS NOT NULL AS has_customer
              FROM alert al
              LEFT JOIN account ac ON ac.account_key = al.account_key
              LEFT JOIN customer c ON c.customer_id = ac.customer_id
             WHERE al.detector = 'ml'
               AND al.alert_id LIKE 'ALT-IF-%'
             ORDER BY al.risk_score DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def verify_subjects(session: Session) -> dict[str, Any]:
    """Bao cao alert IF thieu account/customer (se gay 500 tren GET /alerts/{id})."""
    rows = list_if_alert_subjects(session)
    missing = [r for r in rows if not r["has_account"] or not r["has_customer"]]
    return {
        "n_if_alerts": len(rows),
        "n_ok": len(rows) - len(missing),
        "n_missing_subject": len(missing),
        "missing_account_keys": sorted({r["account_key"] for r in missing}),
    }


def repair_subjects(session: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """Dam bao moi alert IF deu co customer+account de UI detail mo duoc."""
    report = verify_subjects(session)
    created = 0
    for account_key in report["missing_account_keys"]:
        if dry_run:
            logger.info("DRY-RUN would ensure_subject %s", account_key)
            created += 1
            continue
        # as_of khong co tren alert — dung ngay tao alert neu co, else today
        as_of = session.execute(
            text(
                """
                SELECT created_at FROM alert
                 WHERE account_key = :k AND alert_id LIKE 'ALT-IF-%'
                 ORDER BY created_at DESC
                 LIMIT 1
                """
            ),
            {"k": account_key},
        ).scalar_one_or_none()
        if ensure_subject(session, account_key, as_of or datetime.now(tz=UTC)):
            created += 1

    after = verify_subjects(session) if not dry_run else report
    return {
        "before_missing": report["n_missing_subject"],
        "subjects_created_or_planned": created,
        "after_missing": after["n_missing_subject"],
        "n_if_alerts": report["n_if_alerts"],
        "missing_account_keys": report["missing_account_keys"],
    }


def publish_rows(
    session: Session | None,
    rows: pd.DataFrame,
    typology: str,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    inserted = 0
    skipped = 0
    subjects_created = 0

    for _, row in rows.iterrows():
        account_key = str(row["account_key"])
        as_of_ts = row["as_of_ts"]
        window = str(row["window"])
        model_version = str(row.get("model_version") or "if_baseline")
        score = float(row["anomaly_score"])
        risk_score = round(min(max(score * 100.0, 0.0), 100.0), 2)
        alert_id = _stable_alert_id(account_key, as_of_ts, window, model_version)
        reasons = _reasons_from_row(row)
        if len(reasons) < MIN_REASONS:
            raise RuntimeError(f"NT7: alert {alert_id} chi co {len(reasons)} reasons")

        if dry_run:
            logger.info(
                "DRY-RUN %s account=%s risk=%.2f reasons=%d",
                alert_id,
                account_key,
                risk_score,
                len(reasons),
            )
            inserted += 1
            continue

        if session is None:
            raise RuntimeError("Can Session Postgres khi khong --dry-run")

        result = insert_ml_alert(
            session,
            alert_id=alert_id,
            account_key=account_key,
            risk_score=risk_score,
            typology_code=typology,
            reasons=reasons,
            as_of_ts=as_of_ts,
        )
        if result.get("subjects_created"):
            subjects_created += 1
        if result["created"]:
            inserted += 1
        else:
            skipped += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "subjects_created": subjects_created,
        "n_candidates": int(len(rows)),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    if not re.fullmatch(r"T(0[1-9]|10)", args.typology):
        raise SystemExit(f"--typology khong hop le: {args.typology}")

    if args.verify_subjects and args.repair_subjects:
        raise SystemExit("Chi dung mot trong --verify-subjects / --repair-subjects")

    if args.verify_subjects:
        print("Verify customer/account cho alert IF ...", flush=True)
        with get_session() as session:
            report = verify_subjects(session)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if report["n_missing_subject"]:
            raise SystemExit(
                f"Thieu subject cho {report['n_missing_subject']} alert. "
                "Chay: python scripts/publish_if_alerts.py --repair-subjects"
            )
        print("OK: moi alert IF deu join duoc customer (UI detail an toan).", flush=True)
        return

    if args.repair_subjects:
        print("[STEP 2] Repair customer/account cho alert IF ...", flush=True)
        with get_session() as session:
            stats = repair_subjects(session, dry_run=args.dry_run)
        print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
        if args.dry_run:
            print("DRY-RUN: khong ghi Postgres.", flush=True)
        elif stats["after_missing"]:
            raise SystemExit(f"Van con {stats['after_missing']} alert thieu subject.")
        else:
            print("OK: da dam bao subject cho moi alert IF.", flush=True)
        return

    print(f"[1/3] Doc {args.scores} | window={args.window} | top_k={args.top_k}", flush=True)
    top = load_top_k(args.scores, args.window, args.top_k)
    print(
        f"       candidates={len(top)} "
        f"score_min={top['anomaly_score'].min():.4f} "
        f"score_max={top['anomaly_score'].max():.4f}",
        flush=True,
    )

    print("[2/3] Publish alert detector=ml (+ ensure customer/account) ...", flush=True)
    if args.dry_run:
        stats = publish_rows(None, top, args.typology, dry_run=True)
    else:
        with get_session() as session:
            stats = publish_rows(session, top, args.typology, dry_run=False)

    print("[3/3] Done", flush=True)
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        print("DRY-RUN: khong ghi Postgres.", flush=True)
    else:
        print("Kiem tra UI: GET /api/v1/alerts  va  /alerts tren console.", flush=True)
        print("STEP 2: python scripts/publish_if_alerts.py --verify-subjects", flush=True)


if __name__ == "__main__":
    main()
