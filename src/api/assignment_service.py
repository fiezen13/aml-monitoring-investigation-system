"""Dịch vụ phân công — nơi DUY NHẤT ghi việc "hồ sơ này thuộc về ai".

Trước module này có hai đường ghi: màn hình gọi một hàm, trợ lý gọi một hàm
khác, và chúng kiểm khác nhau. Đó là cách hai lối vào của cùng một nghiệp vụ
trôi dần ra xa: một bên chặn giao việc cho Quản lý, bên kia không; một bên ghi
lý do vào nhật ký, bên kia ghi kiểu khác. Sau vài tháng không ai còn trả lời
được "luật thật sự là gì".

Nay cả hai gọi vào đây. Trợ lý và giao diện chỉ là hai LỐI VÀO; luật nghiệp vụ,
phép kiểm tranh chấp và vết kiểm toán nằm ở một chỗ.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import text

#: Trạng thái vụ việc đã kết thúc — không giao việc được nữa.
CLOSED_CASE_STATES = ("XuatHoSo", "DongKhongBaoCao")
_CLOSED_SQL = ", ".join(f"'{s}'" for s in CLOSED_CASE_STATES)


class Source(str, Enum):  # noqa: UP042 — giữ str Enum cho Python 3.10
    """Đường tạo ra một lượt phân công.

    Người chịu trách nhiệm LUÔN là con người đã bấm nút — kể cả khi phương án do
    trợ lý soạn. Trường này nói việc đó tới bằng đường nào, không nói ai chịu
    trách nhiệm.
    """

    MANUAL = "manual"
    AI_COPILOT = "ai_copilot"


class AssignmentError(Exception):
    """Thao tác không thực hiện được, kèm câu giải thích cho người dùng."""

    def __init__(self, code: str, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class CaseSnapshot:
    case_id: str
    state: str
    assigned_to: str | None
    priority: str
    due_at: datetime | None


def _audit(
    session: Any,
    *,
    case_id: str,
    event_type: str,
    actor: str,
    actor_role: str,
    source: Source,
    payload: dict[str, Any],
) -> None:
    """Một mốc nghiệp vụ. Luôn kèm giá trị TRƯỚC và SAU.

    Nhật ký chỉ ghi "đã đổi hạn" thì sáu tháng sau không ai dựng lại được hồ sơ
    từng có hạn nào; ghi cả hai đầu thì lịch sử đọc được như một câu chuyện.
    """
    session.execute(
        text(
            """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
               VALUES (:case_id, :event_type, :actor, :role, CAST(:payload AS jsonb))"""
        ),
        {
            "case_id": case_id,
            "event_type": event_type,
            "actor": actor,
            "role": actor_role,
            "payload": json.dumps({"source": source.value, **payload}, ensure_ascii=False, default=str),
        },
    )


def lock_case(session: Any, case_id: str) -> CaseSnapshot:
    """Đọc và KHOÁ một vụ việc trong phạm vi giao dịch hiện tại.

    Khoá hàng là chốt chống tranh chấp: hai quản lý cùng giao một hồ sơ thì một
    người phải chờ, và khi tới lượt họ thì `assigned_to` đã đổi — phép kiểm
    ``expected_assignee`` bên dưới bắt được ngay.
    """
    row = (
        session.execute(
            text(
                """SELECT case_id, state, assigned_to, priority, due_at
                     FROM aml_case WHERE case_id = :c FOR UPDATE"""
            ),
            {"c": case_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AssignmentError("case_not_found", f"Không tìm thấy hồ sơ {case_id}", status=404)
    return CaseSnapshot(
        case_id=row["case_id"],
        state=row["state"],
        assigned_to=row["assigned_to"],
        priority=row["priority"],
        due_at=row["due_at"],
    )


def resolve_assignee(session: Any, assignee_id: str) -> dict[str, Any]:
    """Người nhận phải là CHUYÊN VIÊN đang hoạt động.

    Quản lý chốt hồ sơ, không lập hồ sơ; giao vụ cho một Quản lý là đưa người
    phê duyệt vào vị trí người lập, đúng thứ nguyên tắc bốn mắt ngăn.
    """
    row = (
        session.execute(
            text("SELECT user_id, name, role, active FROM app_user WHERE user_id = :u"),
            {"u": assignee_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AssignmentError("assignee_not_found", "Không tìm thấy chuyên viên này", status=404)
    if not row["active"]:
        raise AssignmentError("assignee_inactive", "Tài khoản đã bị khoá, không giao việc được")
    if row["role"] != "analyst":
        raise AssignmentError("assignee_not_analyst", "Chỉ giao vụ việc cho Chuyên viên")
    return dict(row)


def assign(
    session: Any,
    *,
    case_id: str,
    assignee_id: str | None,
    actor: str,
    actor_role: str,
    source: Source,
    reason: str,
    expected_assignee: str | None = None,
    check_stale: bool = False,
) -> dict[str, Any]:
    """Giao, chuyển giao, hoặc thu hồi (``assignee_id=None``) một hồ sơ.

    ``check_stale`` bật thì so người xử lý hiện tại với ``expected_assignee`` —
    thứ mà người dùng NHÌN THẤY lúc bấm. Lệch nghĩa là có người khác vừa động
    vào giữa chừng; báo xung đột chứ không ghi đè, vì ghi đè ở đây là âm thầm
    cướp việc của đồng nghiệp.
    """
    case = lock_case(session, case_id)
    if case.state in CLOSED_CASE_STATES:
        raise AssignmentError("case_closed", "Hồ sơ đã kết thúc, không giao việc được nữa")
    if check_stale and case.assigned_to != expected_assignee:
        raise AssignmentError(
            "stale_assignment",
            "Hồ sơ này vừa được người khác cập nhật. Dữ liệu đã được làm mới, bạn xem lại rồi thao tác tiếp.",
        )
    if assignee_id:
        resolve_assignee(session, assignee_id)

    session.execute(
        text(
            # Ép kiểu tường minh: Postgres không suy được kiểu của tham số nằm
            # trong `CASE WHEN ... IS NULL`, và thu hồi việc (`who` = NULL) là
            # một nhánh hợp lệ chứ không phải trường hợp hiếm.
            """UPDATE aml_case
                  SET assigned_to = CAST(:who AS text),
                      assigned_at = CASE WHEN CAST(:who AS text) IS NULL THEN NULL ELSE now() END,
                      assigned_by = CASE WHEN CAST(:who AS text) IS NULL THEN NULL ELSE CAST(:actor AS text) END,
                      assignment_source = CASE
                          WHEN CAST(:who AS text) IS NULL THEN NULL ELSE CAST(:src AS text) END,
                      updated_at = now()
                WHERE case_id = :c"""
        ),
        {"who": assignee_id, "actor": actor, "src": source.value, "c": case_id},
    )
    _audit(
        session,
        case_id=case_id,
        event_type="case_assigned",
        actor=actor,
        actor_role=actor_role,
        source=source,
        payload={"before": case.assigned_to, "after": assignee_id, "reason": reason},
    )
    return {"case_id": case_id, "before": case.assigned_to, "after": assignee_id}


def update_deadline(
    session: Any,
    *,
    case_id: str,
    due_at: datetime | str | None,
    actor: str,
    actor_role: str,
    source: Source,
) -> dict[str, Any]:
    case = lock_case(session, case_id)
    if case.state in CLOSED_CASE_STATES:
        raise AssignmentError("case_closed", "Hồ sơ đã kết thúc, không đổi hạn được nữa")
    session.execute(
        text("UPDATE aml_case SET due_at = CAST(:d AS timestamptz), updated_at = now() WHERE case_id = :c"),
        {"d": due_at, "c": case_id},
    )
    _audit(
        session,
        case_id=case_id,
        event_type="case_state_changed",
        actor=actor,
        actor_role=actor_role,
        source=source,
        payload={"field": "due_at", "before": case.due_at, "after": due_at},
    )
    return {"case_id": case_id, "due_at": due_at}


def update_priority(
    session: Any,
    *,
    case_id: str,
    priority: str,
    actor: str,
    actor_role: str,
    source: Source,
) -> dict[str, Any]:
    case = lock_case(session, case_id)
    if case.state in CLOSED_CASE_STATES:
        raise AssignmentError("case_closed", "Hồ sơ đã kết thúc, không đổi mức ưu tiên được nữa")
    session.execute(
        text("UPDATE aml_case SET priority = :p, updated_at = now() WHERE case_id = :c"),
        {"p": priority, "c": case_id},
    )
    _audit(
        session,
        case_id=case_id,
        event_type="case_state_changed",
        actor=actor,
        actor_role=actor_role,
        source=source,
        payload={"field": "priority", "before": case.priority, "after": priority},
    )
    return {"case_id": case_id, "priority": priority}


def add_note(
    session: Any,
    *,
    case_id: str,
    body: str,
    kind: str,
    actor: str,
    actor_role: str,
    source: Source,
) -> dict[str, Any]:
    """Chỉ dẫn hoặc lời nhắc gửi cho chuyên viên đang giữ hồ sơ."""
    session.execute(
        text("INSERT INTO case_note(case_id, kind, body, author) VALUES (:c, :k, :b, :a)"),
        {"c": case_id, "k": kind, "b": body, "a": actor},
    )
    _audit(
        session,
        case_id=case_id,
        event_type="case_state_changed",
        actor=actor,
        actor_role=actor_role,
        source=source,
        payload={"field": kind, "body": body[:500]},
    )
    return {"case_id": case_id, "kind": kind}
