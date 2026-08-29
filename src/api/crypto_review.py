"""Hàng đợi rà soát giao dịch tiền mã hoá.

Tách khỏi vụ việc ngân hàng vì dữ liệu Elliptic đã ẩn danh: chỉ có mã giao dịch
và đặc trưng đồ thị, không địa chỉ ví, không khách hàng, không tài khoản. Một
"vụ việc" không có chủ thể thì chuỗi điều tra không có gì để truy vấn và hồ sơ
SAR không có ai để báo cáo — xem chú thích của migration 051.

Luồng ba bước, cố ý ngắn: tiếp nhận → đang rà soát → kết luận. Kết luận là của
CON NGƯỜI; mô hình chỉ chấm điểm và giải thích.
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.api.permissions import Permission, has_permission
from src.db.session import get_session

router = APIRouter()

#: Nhãn trạng thái. Mã ở máy chủ, câu chữ ở giao diện — nhưng giữ bảng này để
#: nhật ký kiểm toán đọc được mà không phải tra chỗ khác.
STATES = ("TiepNhan", "DangRaSoat", "KetLuan")


class OpenReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AssignReviewRequest(BaseModel):
    assignee_id: str | None = None
    reason: str = Field(default="", max_length=500)


class ConcludeRequest(BaseModel):
    conclusion: Literal["dang_ngo", "khong_dang_ngo"]
    #: Bắt buộc, và ràng buộc ở cơ sở dữ liệu cũng bắt buộc: một kết luận không
    #: nói vì sao thì không dựng lại được về sau.
    note: str = Field(..., min_length=5, max_length=2000)


def _user(authorization: str | None) -> dict[str, Any]:
    from src.api.routes import _require_user

    return _require_user(authorization)


def _audit(session: Any, *, event_type: str, actor: str, actor_role: str, payload: dict[str, Any]) -> None:
    """Vết đi chung ``audit_log``; ``case_id`` để trống vì đây không phải vụ việc."""
    session.execute(
        text(
            """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
               VALUES (NULL, :e, :a, :r, CAST(:p AS jsonb))"""
        ),
        {
            "e": event_type,
            "a": actor,
            "r": actor_role,
            "p": json.dumps({"source": "crypto_review", **payload}, ensure_ascii=False, default=str),
        },
    )


def _row(r: Any) -> dict[str, Any]:
    return {
        "review_id": r["review_id"],
        "tx_id": r["tx_id"],
        "state": r["state"],
        "risk_level": r["risk_level"],
        "illicit_prob": float(r["illicit_prob"]) if r["illicit_prob"] is not None else None,
        "assignee_id": r["assigned_to"],
        "assignee_name": r["assignee_name"],
        "opened_by_name": r["opened_by_name"],
        "opened_at": r["opened_at"],
        "conclusion": r["conclusion"],
        "conclusion_note": r["conclusion_note"],
        "concluded_by_name": r["concluded_by_name"],
        "concluded_at": r["concluded_at"],
    }


_SELECT = """SELECT v.review_id, v.tx_id, v.state, v.risk_level, v.illicit_prob,
                    v.assigned_to, v.opened_at, v.conclusion, v.conclusion_note,
                    v.concluded_at,
                    u.name AS assignee_name, o.name AS opened_by_name, k.name AS concluded_by_name
               FROM crypto_review v
               LEFT JOIN app_user u ON u.user_id = v.assigned_to
               LEFT JOIN app_user o ON o.user_id = v.opened_by
               LEFT JOIN app_user k ON k.user_id = v.concluded_by"""


@router.get("/fc/crypto-reviews")
def list_reviews(
    state: Literal["TiepNhan", "DangRaSoat", "KetLuan"] | None = Query(default=None),
    mine: bool = Query(default=False, description="Chỉ lượt rà soát giao cho tôi"),
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    """Hàng đợi rà soát. Chuyên viên thấy toàn hàng đợi như với cảnh báo ngân hàng.

    Khác với hồ sơ SAR — thứ mang kết luận và danh tính khách hàng — hàng đợi
    này chỉ là giao dịch công khai trên chuỗi khối đã được chấm điểm, nên không
    có lý do giấu giữa các chuyên viên.
    """
    user = _user(authorization)
    where, params = ["TRUE"], {"limit": limit}
    if state:
        where.append("v.state = :state")
        params["state"] = state
    if mine:
        where.append("v.assigned_to = :me")
        params["me"] = user["user_id"]
    sql = f"{_SELECT} WHERE {' AND '.join(where)} ORDER BY v.opened_at DESC LIMIT :limit"
    with get_session() as session:
        rows = session.execute(text(sql), params).mappings().all()
    return [_row(r) for r in rows]


@router.post("/fc/bitcoin/{tx_id}/review")
def open_review(
    tx_id: str,
    # Thân yêu cầu KHÔNG bắt buộc: mở một lượt rà soát chẳng cần tham số nào, và
    # bắt gửi `{}` chỉ để hợp lệ hoá là làm khó nơi gọi mà không được gì.
    request: OpenReviewRequest | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Đưa một giao dịch vào hàng đợi rà soát.

    Điểm và giải thích của mô hình được chụp lại ngay lúc mở: bản chấm điểm có
    thể được nạp lại theo release mới, và một lượt rà soát phải giữ được con số
    mà người mở nó đã nhìn thấy.
    """
    user = _user(authorization)
    if not has_permission(user["role"], Permission.INVESTIGATE_CASE):
        raise HTTPException(status_code=403, detail="Vai trò hiện tại không mở được lượt rà soát")
    from src.api.routes import _audit_role

    with get_session() as session:
        scored = (
            session.execute(
                text("SELECT risk_level, illicit_prob FROM bitcoin_scored_tx WHERE tx_id = :t"),
                {"t": tx_id},
            )
            .mappings()
            .first()
        )
        if scored is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy giao dịch {tx_id}")
        existing = session.execute(
            text("SELECT review_id FROM crypto_review WHERE tx_id = :t AND state <> 'KetLuan'"),
            {"t": tx_id},
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Giao dịch này đã nằm trong hàng đợi rà soát")

        review_id = f"CR-{secrets.token_hex(6)}"
        session.execute(
            text(
                """INSERT INTO crypto_review(review_id, tx_id, risk_level, illicit_prob, opened_by)
                   VALUES (:id, :t, :lv, :p, :by)"""
            ),
            {
                "id": review_id,
                "t": tx_id,
                "lv": scored["risk_level"],
                "p": scored["illicit_prob"],
                "by": user["user_id"],
            },
        )
        _audit(
            session,
            event_type="crypto_review_opened",
            actor=user["user_id"],
            actor_role=_audit_role(user["role"]),
            payload={"review_id": review_id, "tx_id": tx_id, "risk_level": scored["risk_level"]},
        )
        row = session.execute(text(f"{_SELECT} WHERE v.review_id = :id"), {"id": review_id}).mappings().one()
    return _row(row)


@router.post("/fc/crypto-reviews/{review_id}/assign")
def assign_review(
    review_id: str, request: AssignReviewRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Nhận lượt rà soát về mình, trả lại hàng đợi, hoặc giao cho người khác.

    Chuyên viên chỉ TỰ NHẬN hoặc trả lại lượt của chính mình — cùng luật với
    hàng đợi vụ việc ngân hàng, để hai nơi không dạy người dùng hai thói quen.
    """
    user = _user(authorization)
    from src.api.routes import _audit_role

    assignee = (request.assignee_id or "").strip() or None
    can_coordinate = has_permission(user["role"], Permission.SAR_ASSIGN)
    with get_session() as session:
        row = (
            session.execute(
                text("SELECT review_id, state, assigned_to FROM crypto_review WHERE review_id = :id FOR UPDATE"),
                {"id": review_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy lượt rà soát")
        if row["state"] == "KetLuan":
            raise HTTPException(status_code=409, detail="Lượt rà soát đã kết luận")
        if not can_coordinate:
            if assignee not in (None, user["user_id"]):
                raise HTTPException(status_code=403, detail="Chuyên viên chỉ tự nhận lượt rà soát cho mình")
            if assignee is None and row["assigned_to"] != user["user_id"]:
                raise HTTPException(status_code=403, detail="Chỉ trả lại được lượt của chính mình")
        if assignee:
            target = (
                session.execute(text("SELECT role, active FROM app_user WHERE user_id = :u"), {"u": assignee})
                .mappings()
                .first()
            )
            if target is None or not target["active"]:
                raise HTTPException(status_code=404, detail="Không tìm thấy chuyên viên đang hoạt động")
            if target["role"] != "analyst":
                raise HTTPException(status_code=409, detail="Chỉ giao lượt rà soát cho Chuyên viên")

        session.execute(
            text(
                """UPDATE crypto_review
                      SET assigned_to = CAST(:a AS text),
                          state = CASE WHEN CAST(:a AS text) IS NULL THEN 'TiepNhan' ELSE 'DangRaSoat' END,
                          updated_at = now()
                    WHERE review_id = :id"""
            ),
            {"a": assignee, "id": review_id},
        )
        _audit(
            session,
            event_type="crypto_review_assigned",
            actor=user["user_id"],
            actor_role=_audit_role(user["role"]),
            payload={
                "review_id": review_id,
                "before": row["assigned_to"],
                "after": assignee,
                "reason": request.reason,
            },
        )
        out = session.execute(text(f"{_SELECT} WHERE v.review_id = :id"), {"id": review_id}).mappings().one()
    return _row(out)


@router.post("/fc/crypto-reviews/{review_id}/conclude")
def conclude_review(
    review_id: str, request: ConcludeRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Ghi kết luận của con người và đóng lượt rà soát.

    Chỉ người ĐANG GIỮ lượt mới kết luận được. Kết luận là phán đoán nghiệp vụ,
    và người đưa ra nó phải là người đã đọc hồ sơ.
    """
    user = _user(authorization)
    from src.api.routes import _audit_role

    with get_session() as session:
        row = (
            session.execute(
                text("SELECT state, assigned_to, tx_id FROM crypto_review WHERE review_id = :id FOR UPDATE"),
                {"id": review_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy lượt rà soát")
        if row["state"] == "KetLuan":
            raise HTTPException(status_code=409, detail="Lượt rà soát này đã kết luận")
        if row["assigned_to"] != user["user_id"] and not has_permission(user["role"], Permission.SAR_ASSIGN):
            raise HTTPException(status_code=403, detail="Chỉ người đang rà soát mới ghi được kết luận")

        session.execute(
            text(
                """UPDATE crypto_review
                      SET state = 'KetLuan', conclusion = :c, conclusion_note = :n,
                          concluded_by = :by, concluded_at = now(), updated_at = now()
                    WHERE review_id = :id"""
            ),
            {"c": request.conclusion, "n": request.note.strip(), "by": user["user_id"], "id": review_id},
        )
        _audit(
            session,
            event_type="crypto_review_concluded",
            actor=user["user_id"],
            actor_role=_audit_role(user["role"]),
            payload={
                "review_id": review_id,
                "tx_id": row["tx_id"],
                "conclusion": request.conclusion,
                "note": request.note.strip()[:500],
            },
        )
        out = session.execute(text(f"{_SELECT} WHERE v.review_id = :id"), {"id": review_id}).mappings().one()
    return _row(out)
