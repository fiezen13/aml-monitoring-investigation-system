"""Chạy bộ luật trên dữ liệu giao dịch và sinh cảnh báo ``detector='rule'``.

Phân vai:

* SQL lo phần gom số liệu — hàng triệu giao dịch, phải để cơ sở dữ liệu làm.
* Python lo phần quyết định — ``src/detection/rules.py`` đọc được như văn bản
  quy định, và có thể kiểm bằng unit test mà không cần cơ sở dữ liệu.

Đầu ra bền vững của nhánh rule gồm ba bảng: ``alert``, ``alert_reason`` và
``alert_typology_match``. **Không** ghi ``detection_result``: bảng đó có khoá
ngoại NOT NULL trỏ tới ``behavior_feature_snapshot``, tức nó được thiết kế cho
các nhánh chạy theo lô đặc trưng behaviour. Nhánh rule không sinh ảnh chụp đặc
trưng, và tạo một ảnh chụp rỗng chỉ để thoả khoá ngoại là bịa dữ liệu. Muốn
nhánh rule vào bảng đó thì phải nới lược đồ trước — xem
``docs/specification/technical-design.md §3``.

Cửa sổ dùng dạng nửa kín ``[as_of - window, as_of)``, giống hệt quy ước của
nhánh graph và nhánh behaviour, để ba nhánh nói về cùng một khoảng thời gian.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.detection.rules import (
    RULE_THRESHOLDS,
    RULE_WEIGHT,
    RuleContext,
    RuleHit,
    evaluate,
    risk_score,
    should_alert,
    signals_of,
)
from src.investigation.typology_match import match_typology
from src.services.if_alert_publish import ensure_subject, record_typology_match

logger = logging.getLogger("fin07.rule_engine")

DETECTOR_ID = "fin07_rule_engine"
DETECTOR_VERSION = "rules_v1"

#: Tối thiểu 3 dòng ``alert_reason`` cho mỗi cảnh báo (ràng buộc NT7). Khi số
#: luật kích hoạt ít hơn, ta bù bằng các dòng ngữ cảnh có thật — KHÔNG bịa thêm
#: luật. Xem ``_context_reasons``.
MIN_REASONS = 3


def stable_rule_alert_id(account_key: str, as_of: datetime, window_days: int) -> str:
    raw = f"{account_key}|{as_of.isoformat()}|{window_days}d|{DETECTOR_VERSION}|rule"
    return "ALT-RULE-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


#: Gom số liệu cho mọi tài khoản có phát sinh trong cửa sổ.
#:
#: Một lượt quét bảng giao dịch, không lặp mỗi tài khoản một truy vấn: với vài
#: triệu dòng thì lặp là bất khả thi.
_AGGREGATE_SQL = """
WITH win AS (
    SELECT t.transaction_id, t.occurred_at, t.from_account_key, t.to_account_key,
           t.amount::double precision AS amount,
           fb.country_code AS from_country, tb.country_code AS to_country,
           fb.is_vasp AS from_vasp, tb.is_vasp AS to_vasp
      FROM transaction t
      LEFT JOIN bank fb ON fb.bank_code = split_part(t.from_account_key, ':', 1)
      LEFT JOIN bank tb ON tb.bank_code = split_part(t.to_account_key, ':', 1)
     WHERE t.occurred_at >= :window_start AND t.occurred_at < :as_of
),
-- Mỗi giao dịch xuất hiện hai lần: một lần cho bên gửi, một lần cho bên nhận.
sided AS (
    SELECT from_account_key AS account_key, 'out' AS direction, occurred_at, amount,
           to_country AS counterparty_country, from_country AS own_country,
           to_vasp AS counterparty_vasp
      FROM win
    UNION ALL
    SELECT to_account_key AS account_key, 'in' AS direction, occurred_at, amount,
           from_country AS counterparty_country, to_country AS own_country,
           from_vasp AS counterparty_vasp
      FROM win
),
near AS (
    SELECT account_key,
           count(*) AS near_count,
           count(DISTINCT round(amount::numeric, 2)) AS near_distinct,
           EXTRACT(EPOCH FROM (max(occurred_at) - min(occurred_at))) / 3600.0 AS near_span_hours
      FROM sided
     WHERE direction = 'out'
       AND amount >= :band_floor AND amount < :threshold
     GROUP BY account_key
),
agg AS (
    SELECT account_key,
           count(*) FILTER (WHERE direction = 'out') AS outgoing_count,
           count(*) FILTER (WHERE direction = 'in') AS incoming_count,
           coalesce(sum(amount) FILTER (WHERE direction = 'out'), 0) AS total_outflow,
           coalesce(sum(amount) FILTER (WHERE direction = 'in'), 0) AS total_inflow,
           count(*) AS transaction_count,
           count(*) FILTER (
               WHERE counterparty_country IS NOT NULL AND own_country IS NOT NULL
                 AND counterparty_country <> own_country
           ) AS cross_border_count,
           count(*) FILTER (WHERE counterparty_vasp) AS vasp_transaction_count,
           coalesce(sum(amount) FILTER (WHERE counterparty_vasp), 0) AS vasp_amount
      FROM sided
     GROUP BY account_key
)
SELECT a.account_key, a.outgoing_count, a.incoming_count, a.total_outflow, a.total_inflow,
       a.transaction_count, a.cross_border_count, a.vasp_transaction_count, a.vasp_amount,
       coalesce(n.near_count, 0) AS near_count,
       coalesce(n.near_distinct, 0) AS near_distinct,
       coalesce(n.near_span_hours, 0) AS near_span_hours
  FROM agg a
  LEFT JOIN near n ON n.account_key = a.account_key
 WHERE a.transaction_count >= :min_transactions
 ORDER BY a.account_key
"""

#: Tiền ra trong vòng 2 giờ sau lần nhận gần nhất, và thời gian giữ tiền trung
#: vị. Tách riêng vì cần so từng cặp vào/ra theo thời gian — không gộp chung
#: được với các phép đếm ở trên.
_RAPID_SQL = """
WITH win AS (
    SELECT occurred_at, from_account_key, to_account_key, amount::double precision AS amount
      FROM transaction
     WHERE occurred_at >= :window_start AND occurred_at < :as_of
),
sided AS (
    SELECT from_account_key AS account_key, 'out' AS direction, occurred_at, amount FROM win
    UNION ALL
    SELECT to_account_key AS account_key, 'in' AS direction, occurred_at, amount FROM win
),
marked AS (
    SELECT account_key, direction, occurred_at, amount,
           max(occurred_at) FILTER (WHERE direction = 'in')
               OVER (PARTITION BY account_key ORDER BY occurred_at
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS last_inflow_at
      FROM sided
)
SELECT account_key,
       coalesce(sum(amount) FILTER (
           WHERE direction = 'out' AND last_inflow_at IS NOT NULL
             AND occurred_at - last_inflow_at <= interval '2 hours'
       ), 0) AS rapid_outflow_amount,
       percentile_cont(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (occurred_at - last_inflow_at)) / 3600.0
       ) FILTER (WHERE direction = 'out' AND last_inflow_at IS NOT NULL) AS median_dwell_hours
  FROM marked
 GROUP BY account_key
"""


def iter_contexts(
    session: Session,
    *,
    as_of: datetime,
    window_days: int,
    min_transactions: int,
) -> Iterator[RuleContext]:
    """Dựng quan sát cho từng tài khoản có phát sinh trong cửa sổ."""
    window_start = as_of - timedelta(days=window_days)
    params = {
        "as_of": as_of,
        "window_start": window_start,
        "threshold": RULE_THRESHOLDS["reporting_threshold"],
        "band_floor": RULE_THRESHOLDS["reporting_threshold"] * RULE_THRESHOLDS["structuring_band_floor"],
        "min_transactions": min_transactions,
    }

    rapid = {
        row["account_key"]: (row["rapid_outflow_amount"], row["median_dwell_hours"])
        for row in session.execute(text(_RAPID_SQL), {"as_of": as_of, "window_start": window_start}).mappings()
    }

    for row in session.execute(text(_AGGREGATE_SQL), params).mappings():
        rapid_amount, dwell = rapid.get(row["account_key"], (0.0, None))
        yield RuleContext(
            account_key=row["account_key"],
            as_of=as_of,
            window_days=window_days,
            outgoing_count=int(row["outgoing_count"]),
            incoming_count=int(row["incoming_count"]),
            total_outflow=float(row["total_outflow"]),
            total_inflow=float(row["total_inflow"]),
            near_threshold_count=int(row["near_count"]),
            near_threshold_distinct_amounts=int(row["near_distinct"]),
            near_threshold_span_hours=float(row["near_span_hours"]),
            rapid_outflow_amount=float(rapid_amount or 0.0),
            median_dwell_hours=float(dwell) if dwell is not None else None,
            vasp_amount=float(row["vasp_amount"]),
            vasp_transaction_count=int(row["vasp_transaction_count"]),
            cross_border_count=int(row["cross_border_count"]),
            transaction_count=int(row["transaction_count"]),
        )


def _context_reasons(ctx: RuleContext, hits: list[RuleHit]) -> list[dict[str, Any]]:
    """Bù cho đủ số dòng ``alert_reason`` bằng ngữ cảnh có thật.

    Ràng buộc NT7 đòi tối thiểu ba dòng, nhưng một cảnh báo có thể chỉ vi phạm
    một luật. Thay vì bịa thêm luật, ta thêm các số đo đã dùng để đánh giá —
    chúng vẫn là dữ kiện kiểm chứng được, và ``weight = 0`` nói rõ chúng không
    góp vào điểm.
    """
    context = [
        ("CTX_TRANSACTION_COUNT", "Số giao dịch trong cửa sổ", float(ctx.transaction_count)),
        ("CTX_OUTFLOW_TOTAL", "Tổng tiền ra trong cửa sổ", round(ctx.total_outflow, 2)),
        ("CTX_INFLOW_TOTAL", "Tổng tiền vào trong cửa sổ", round(ctx.total_inflow, 2)),
        ("CTX_WINDOW_DAYS", "Độ dài cửa sổ quan sát (ngày)", float(ctx.window_days)),
    ]
    needed = max(0, MIN_REASONS - len(hits))
    return [
        {"factor_code": code, "factor_label": label, "contribution": 0.0, "weight": 0.0, "value": value}
        for code, label, value in context[:needed]
    ]


def publish_rule_alert(
    session: Session,
    ctx: RuleContext,
    hits: list[RuleHit],
) -> dict[str, Any] | None:
    """Ghi một cảnh báo rule kèm luật đã kích hoạt và nhóm hành vi suy ra.

    Idempotent theo ``alert_id``. Gọi trong ``with get_session()`` để cảnh báo và
    các dòng lý do nằm trong cùng một giao dịch cơ sở dữ liệu.
    """
    if not should_alert(hits):
        return None

    alert_id = stable_rule_alert_id(ctx.account_key, ctx.as_of, ctx.window_days)
    if session.execute(text("SELECT 1 FROM alert WHERE alert_id = :a"), {"a": alert_id}).scalar_one_or_none():
        return {"alert_id": alert_id, "created": False}

    ensure_subject(session, ctx.account_key, ctx.as_of)

    match = match_typology(signals_of(hits))
    score = risk_score(hits)

    session.execute(
        text(
            """INSERT INTO alert (
                   alert_id, account_key, transaction_id, typology_code, detector,
                   risk_score, status, case_id, created_at
               ) VALUES (
                   :alert_id, :account_key, NULL, :typology_code, 'rule',
                   :risk_score, 'open', NULL, :created_at
               )"""
        ),
        {
            "alert_id": alert_id,
            "account_key": ctx.account_key,
            "typology_code": match.typology_code,
            "risk_score": score,
            "created_at": ctx.as_of,
        },
    )

    reasons: list[dict[str, Any]] = [
        {
            "factor_code": hit.code,
            "factor_label": hit.label[:500],
            "contribution": round(hit.contribution, 2),
            "weight": round(hit.weight, 2),
        }
        for hit in hits
    ]
    reasons.extend({k: v for k, v in reason.items() if k != "value"} for reason in _context_reasons(ctx, hits))
    for reason in reasons:
        session.execute(
            text(
                """INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
                   VALUES (:alert_id, :factor_code, :factor_label, :contribution, :weight)
                   ON CONFLICT (alert_id, factor_code) DO NOTHING"""
            ),
            {"alert_id": alert_id, **reason},
        )

    record_typology_match(session, alert_id, match)
    return {
        "alert_id": alert_id,
        "created": True,
        "risk_score": score,
        "typology_code": match.typology_code,
        "rules": [hit.code for hit in hits],
    }


def default_as_of(session: Session) -> datetime | None:
    """Mốc kết thúc cửa sổ mặc định — chọn theo mật độ dữ liệu, không theo mốc lớn nhất.

    Cả LI-Small lẫn HI-Medium đều dồn gần hết giao dịch vào vài ngày đầu rồi để
    lại một đuôi thưa kéo dài. Lấy ``max(occurred_at)`` sẽ đặt cửa sổ đúng vào
    đuôi rỗng đó: trên HI-Medium, cửa sổ 7 ngày cuối chỉ chứa 850 trong 5,86
    triệu giao dịch, và bộ luật quét được 47 tài khoản.

    Ở đây ta lấy mốc của **giao dịch thứ 99 phần trăm** rồi cộng một giây, nên
    cửa sổ luôn nằm trong vùng dày dữ liệu bất kể đuôi dài bao nhiêu.
    """
    cutoff = session.execute(
        text(
            """SELECT percentile_disc(0.99) WITHIN GROUP (ORDER BY occurred_at)
                 FROM transaction"""
        )
    ).scalar_one_or_none()
    return cutoff + timedelta(seconds=1) if cutoff is not None else None


def run(
    session: Session,
    *,
    as_of: datetime | None = None,
    window_days: int = 7,
    min_transactions: int = 5,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Quét một cửa sổ và sinh cảnh báo cho mọi tài khoản vi phạm."""
    if as_of is None:
        as_of = default_as_of(session)
        if as_of is None:
            return {"scanned": 0, "triggered": 0, "created": 0, "as_of": None}
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    window_transactions = int(
        session.execute(
            text(
                """SELECT count(*) FROM transaction
                    WHERE occurred_at >= :start AND occurred_at < :as_of"""
            ),
            {"start": as_of - timedelta(days=window_days), "as_of": as_of},
        ).scalar_one()
    )
    total_transactions = int(session.execute(text("SELECT count(*) FROM transaction")).scalar_one())
    coverage = window_transactions / total_transactions if total_transactions else 0.0
    if coverage < 0.05:
        logger.warning(
            "Cửa sổ chỉ chứa %.2f%% tổng giao dịch (%d/%d). Bộ dữ liệu này dồn hết vào vài ngày "
            "đầu rồi để lại một đuôi gần rỗng; mốc --as-of mặc định rơi vào đuôi đó. "
            "Chọn --as-of nằm trong vùng dày dữ liệu.",
            100 * coverage,
            window_transactions,
            total_transactions,
        )

    scanned = triggered = created = 0
    by_rule: dict[str, int] = {}
    by_typology: dict[str, int] = {}

    for ctx in iter_contexts(session, as_of=as_of, window_days=window_days, min_transactions=min_transactions):
        scanned += 1
        hits = evaluate(ctx)
        if not should_alert(hits):
            continue
        triggered += 1
        for hit in hits:
            by_rule[hit.code] = by_rule.get(hit.code, 0) + 1
        if dry_run:
            continue
        result = publish_rule_alert(session, ctx, hits)
        if result and result["created"]:
            created += 1
            by_typology[result["typology_code"]] = by_typology.get(result["typology_code"], 0) + 1
        if limit is not None and created >= limit:
            break

    return {
        "as_of": as_of.isoformat(),
        "window_days": window_days,
        "window_transactions": window_transactions,
        "window_coverage": round(coverage, 4),
        "scanned": scanned,
        "triggered": triggered,
        "created": created,
        "by_rule": dict(sorted(by_rule.items())),
        "by_typology": dict(sorted(by_typology.items())),
        "rule_weight": RULE_WEIGHT,
    }
