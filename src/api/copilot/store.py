"""Lưu và lấy lại đề xuất hành động.

Tham số của một hành động được giữ Ở MÁY CHỦ giữa hai nhịp. Lúc người dùng bấm
xác nhận, máy chủ đọc lại từ đây — không đọc lại câu tiếng Việt đã sinh ra nó,
và không đọc phần thân yêu cầu do giao diện gửi lên. Đó là điểm khác biệt giữa
"người dùng chấp thuận đúng thứ họ vừa đọc" và "người dùng chấp thuận thứ gì đó
mà trình duyệt vừa gửi".

``payload_hash`` là chốt phát hiện sửa trộm: nếu bản ghi trong cơ sở dữ liệu bị
đổi bằng đường khác, băm không khớp và hành động bị từ chối.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import text

from src.api.copilot.schemas import PROPOSAL_TTL, ActionProposal, ActionType


def new_action_id() -> str:
    return f"ACT-{secrets.token_hex(8)}"


def payload_hash(payload: dict[str, Any]) -> str:
    """Băm ổn định của tham số — khoá thứ tự để hai lần băm cùng ra một kết quả."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def save_proposal(
    session: Any, proposal: ActionProposal, *, requested_by: str, requested_role: str, now: datetime
) -> None:
    payload = proposal.to_payload()
    session.execute(
        text(
            """INSERT INTO copilot_action
                   (action_id, action_type, payload, payload_hash,
                    requested_by, requested_role, status, expires_at)
               VALUES (:id, :type, CAST(:payload AS jsonb), :hash, :by, :role, 'proposed', :expires)"""
        ),
        {
            "id": proposal.action_id,
            "type": proposal.action_type.value,
            "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
            "hash": payload_hash(payload),
            "by": requested_by,
            "role": requested_role,
            "expires": now + PROPOSAL_TTL,
        },
    )


def load_for_update(session: Any, action_id: str) -> dict[str, Any] | None:
    """Đọc và KHOÁ bản ghi.

    Khoá hàng là cách chống bấm hai lần: hai yêu cầu cùng lúc thì một cái phải
    chờ, và khi tới lượt nó thì trạng thái đã là 'executed'.
    """
    row = (
        session.execute(
            text(
                """SELECT action_id, action_type, payload, payload_hash, requested_by,
                          requested_role, status, expires_at, result
                     FROM copilot_action WHERE action_id = :id FOR UPDATE"""
            ),
            {"id": action_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def mark(session: Any, action_id: str, status: str, *, result: dict[str, Any] | None = None) -> None:
    session.execute(
        text(
            """UPDATE copilot_action
                  SET status = :s,
                      executed_at = CASE WHEN :s = 'executed' THEN now() ELSE executed_at END,
                      result = COALESCE(CAST(:r AS jsonb), result)
                WHERE action_id = :id"""
        ),
        {
            "s": status,
            "r": json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
            "id": action_id,
        },
    )


def action_type_of(row: dict[str, Any]) -> ActionType:
    return ActionType(row["action_type"])
