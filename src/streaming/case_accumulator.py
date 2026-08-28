"""Pha 4 — bồi tụ CẢNH BÁO → VỤ VIỆC THẬT (alert + aml_case) theo TỪNG CẠNH.

Đích cuối của streaming là VỤ VIỆC: cái chuyên viên mở, điều tra, xuất SAR. Nên
cảnh báo/vụ việc streaming ghi thẳng vào bảng nghiệp vụ THẬT (`alert`, `aml_case`)
đúng khuôn `mega_pna` mà batch đang dùng — KHÔNG bảng riêng. Nhờ đó trang Cảnh báo/
Vụ việc hiện có, nút Điều tra AI, SAR, phê duyệt… đều chạy được.

Cách ghép (union-find): mỗi cạnh bị gắn cờ tạo một cảnh báo; hai đầu cạnh cùng vào
một vụ; cạnh mới chạm tài khoản đã thuộc vụ → nhập vào vụ đó; nối hai vụ rời → gộp.
Vụ việc LỚN DẦN từng cạnh, đúng cách ngân hàng thật hoạt động.

Chi tiết khớp lược đồ nghiệp vụ:
  * khoá tài khoản CHUẨN HOÁ ISO (UK→GB…) để khớp FK `account`;
  * typology suy từ metric fan-in/fan-out (stream_account_state) — đúng `typology_for`
    của batch, KHÔNG gán bừa;
  * detector='mega_pna', dataset='saml_d', risk_score = điểm×100;
  * vụ mới state='TiepNhanCanhBao' (đầu máy trạng thái 12 bước).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger("fin07.streaming.case_accumulator")

DETECTOR = "mega_pna"
DATASET = "saml_d"

#: Tên quốc gia SAML-D → ISO 3166-1 alpha-2 (khớp scripts/load_saml_d.py). Khoá tài
#: khoản phải là ISO để trùng bảng `account` (FK của alert/aml_case).
ISO2 = {
    "UK": "GB", "USA": "US", "UAE": "AE", "Turkey": "TR", "Switzerland": "CH",
    "Pakistan": "PK", "Nigeria": "NG", "Spain": "ES", "Germany": "DE", "Italy": "IT",
    "France": "FR", "Japan": "JP", "Morocco": "MA", "Austria": "AT", "Mexico": "MX",
    "Albania": "AL", "India": "IN", "Netherlands": "NL",
}


def normalize_account_key(raw: str) -> str:
    """'UK:123' → 'GB:123'. Giữ nguyên nếu đã ISO hoặc không rõ (để lộ ra nếu lệch)."""
    country, sep, acct = raw.partition(":")
    if not sep:
        return raw
    return f"{ISO2.get(country, country)}:{acct}"


def _typology_for(incoming: int, outgoing: int, edges: int) -> tuple[str, str]:
    """Suy nhóm hành vi từ fan-in/fan-out — đúng logic build_mega_pna_alerts."""
    edges = max(1, edges)
    if incoming >= 5 and outgoing >= 5:
        return "T04", "Nhiều nguồn dồn vào rồi toả ra nhiều đích"
    if outgoing >= 3 and incoming >= 1 and outgoing / edges >= 0.7:
        return "T05", "Tiền vào rồi ra ngay trong cửa sổ quan sát"
    if incoming >= 5:
        return "T04", "Nhiều nguồn dồn về một tài khoản"
    return "T02", "Tài khoản trung chuyển trong mạng lưới"


def _priority(risk: float) -> str:
    if risk >= 90:
        return "critical"
    if risk >= 75:
        return "high"
    if risk >= 50:
        return "medium"
    return "low"


def _case_of(session: Any, account: str) -> str | None:
    r = session.execute(text("SELECT case_id FROM stream_case_membership WHERE account_key = :a"),
                        {"a": account}).first()
    return r[0] if r else None


def _exists(session: Any, account: str) -> bool:
    """Tài khoản có trong bảng `account` không (điều kiện FK của alert/aml_case)."""
    return session.execute(text("SELECT 1 FROM account WHERE account_key = :a"), {"a": account}).first() is not None


def _new_case(session: Any, case_id: str, subject: str, risk: float, occurred_at) -> None:
    session.execute(
        text("INSERT INTO aml_case (case_id, subject_account_key, title, state, risk_score, priority, created_at, updated_at) "
             "VALUES (:cid, :subj, :title, 'TiepNhanCanhBao', :risk, :prio, :ts, :ts) ON CONFLICT (case_id) DO NOTHING"),
        {"cid": case_id, "subj": subject, "title": f"Vụ streaming quanh {subject}", "risk": risk,
         "prio": _priority(risk), "ts": occurred_at},
    )


def _merge(session: Any, keep: str, drop: str) -> str:
    """Gộp vụ `drop` vào `keep`: chuyển thành viên + cảnh báo + link, rồi xoá vụ rỗng."""
    if keep == drop:
        return keep
    session.execute(text("UPDATE stream_case_membership SET case_id = :k WHERE case_id = :d"), {"k": keep, "d": drop})
    session.execute(text("UPDATE alert SET case_id = :k WHERE case_id = :d"), {"k": keep, "d": drop})
    session.execute(text("UPDATE stream_alert_link SET case_id = :k WHERE case_id = :d"), {"k": keep, "d": drop})
    # Vụ streaming mới gộp chưa có approval/evidence/... nên xoá an toàn.
    session.execute(text("DELETE FROM aml_case WHERE case_id = :d"), {"d": drop})
    return keep


def _refresh_case(session: Any, case_id: str) -> None:
    """Cập nhật điểm + tài khoản chủ thể của vụ từ các cảnh báo của nó."""
    session.execute(text(
        "UPDATE aml_case c SET risk_score = a.mx, priority = CASE "
        "  WHEN a.mx>=90 THEN 'critical' WHEN a.mx>=75 THEN 'high' WHEN a.mx>=50 THEN 'medium' ELSE 'low' END, "
        "  subject_account_key = a.subj, updated_at = now() "
        "FROM (SELECT max(risk_score) mx, (array_agg(account_key ORDER BY risk_score DESC))[1] subj "
        "      FROM alert WHERE case_id = :c) a WHERE c.case_id = :c"),
        {"c": case_id})


def accumulate(session: Any, scored_edges: Any, dataset: str = DATASET) -> tuple[int, int]:
    """Bồi tụ các ScoredEdge ĐÃ GẮN CỜ (in-mem) vào VỤ VIỆC THẬT (alert + aml_case).

    Không đọc giao dịch thô từ Postgres — raw ở Bronze. Idempotent qua alert_id tất
    định (từ source_id). Dùng chung cho SAML-D (dataset='saml_d') và IBM
    (dataset='ibm_hi_medium'). Trả (cảnh báo mới, số vụ chạm).
    """
    touched: set[str] = set()
    skipped = created = 0
    for e in scored_edges:
        if not getattr(e, "triggered", False):
            continue
        nf = normalize_account_key(e.from_account)
        nt = normalize_account_key(e.to_account)
        # alert/aml_case FK tới `account` → chỉ nhận tài khoản tồn tại (≈1% lệch bị bỏ).
        endpoints = [a for a in (nf, nt) if _exists(session, a)]
        if not endpoints:
            skipped += 1
            continue
        alert_id = "ALT-STREAM-" + hashlib.sha1(str(e.source_id).encode()).hexdigest()[:16]
        if session.execute(text("SELECT 1 FROM alert WHERE alert_id = :a"), {"a": alert_id}).first():
            continue  # đã tạo cảnh báo cho cạnh này (idempotent)
        subject = endpoints[0]
        inc, outc = (e.from_in, e.from_out) if subject == nf else (e.to_in, e.to_out)
        risk = round(min(100.0, max(0.0, float(e.score) * 100.0)), 2)
        cases = [c for c in (_case_of(session, a) for a in endpoints) if c]
        cf = cases[0] if cases else None
        ct = cases[1] if len(cases) > 1 else None
        if cf and ct:
            case_id = _merge(session, cf, ct)
        elif cf:
            case_id = cf
        else:
            case_id = "CASE-STREAM-" + hashlib.sha1(str(e.source_id).encode()).hexdigest()[:12]
            _new_case(session, case_id, subject, risk, e.occurred_at)
        for acct in endpoints:
            session.execute(text("INSERT INTO stream_case_membership (account_key, case_id) VALUES (:a,:c) "
                                 "ON CONFLICT (account_key) DO NOTHING"), {"a": acct, "c": case_id})
        typ, _ = _typology_for(inc, outc, inc + outc)
        session.execute(
            text("INSERT INTO alert (alert_id, account_key, transaction_id, typology_code, detector, "
                 "risk_score, status, case_id, dataset) "
                 "VALUES (:aid, :acct, NULL, :typ, :det, :risk, 'open', :cid, :ds) "
                 "ON CONFLICT (alert_id) DO NOTHING"),
            {"aid": alert_id, "acct": subject, "typ": typ, "det": DETECTOR, "risk": risk, "cid": case_id, "ds": dataset},
        )
        created += 1
        touched.add(case_id)
    for case_id in touched:
        _refresh_case(session, case_id)
    if skipped:
        logger.info("Bỏ qua %d cạnh (tài khoản không có trong `account`).", skipped)
    return created, len(touched)
