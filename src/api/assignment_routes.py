"""Màn "Phân công & tải công việc" — một chỗ duy nhất trả lời hồ sơ đang ở đâu.

Trợ lý AI giúp giao việc nhanh; trang này giúp KIỂM SOÁT toàn bộ công việc. Hai
thứ đọc cùng một bảng và ghi qua cùng một dịch vụ, nên một lượt giao qua trò
chuyện hiện ở đây ngay, không cần đồng bộ gì thêm.

Trạng thái nghiệp vụ được suy ở tầng này chứ không lưu thành cột: "quá hạn" hay
"sắp đến hạn" là quan hệ giữa hạn xử lý và thời điểm hỏi, nên lưu nó ra cột là
tự tạo một sự thật thứ hai cần chạy nền để cập nhật.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text

from src.api import assignment_service as svc
from src.api.permissions import Permission, has_permission
from src.db.session import get_session
from src.models.assignment_schemas import (
    AssignmentDetailOut,
    AssignmentPageOut,
    AssignmentRowOut,
    BulkAssignRequest,
    OverviewOut,
    ReassignRequest,
    WorkloadRowOut,
)

router = APIRouter()

#: "Sắp đến hạn" = còn dưới ngần này. Một ngưỡng, dùng chung cho cả KPI, bộ lọc
#: và nhãn trạng thái — ba nơi tự định nghĩa riêng thì bảng và thẻ đếm lệch nhau.
DUE_SOON = timedelta(hours=24)

_CLOSED = ", ".join(f"'{s}'" for s in svc.CLOSED_CASE_STATES)


def _require(authorization: str | None) -> dict[str, Any]:
    from src.api.routes import _require_user

    return _require_user(authorization)


def _guard(user: dict[str, Any], permission: Permission) -> None:
    """Chốt quyền ở MÁY CHỦ. Giao diện ẩn nút chỉ là tiện dụng."""
    if not has_permission(user["role"], permission):
        raise HTTPException(status_code=403, detail="Tài khoản của bạn không có quyền thực hiện thao tác này")


def _status(assigned_to: str | None, state: str, due_at: datetime | None, now: datetime) -> str:
    """Trạng thái NGHIỆP VỤ của một dòng phân công.

    Suy tại thời điểm hỏi. Thứ tự xét có chủ ý: quá hạn đè lên mọi thứ khác, vì
    đó là điều người quản lý cần thấy trước tiên.
    """
    if state in svc.CLOSED_CASE_STATES:
        return "completed"
    if assigned_to is None:
        return "unassigned"
    if due_at is not None:
        if due_at < now:
            return "overdue"
        if due_at - now <= DUE_SOON:
            return "due_soon"
    if state == "DieuTraBoSung":
        return "needs_info"
    return "in_progress"


def _row(r: Any, now: datetime) -> AssignmentRowOut:
    return AssignmentRowOut(
        case_id=r["case_id"],
        title=r["title"],
        risk_score=round(float(r["risk_score"] or 0), 1),
        priority=r["priority"],
        state=r["state"],
        assignee_id=r["assigned_to"],
        assignee_name=r["assignee_name"],
        assigned_at=r["assigned_at"],
        assigned_by_id=r["assigned_by"],
        assigned_by_name=r["assigned_by_name"],
        source=r["assignment_source"],
        due_at=r["due_at"],
        status=_status(r["assigned_to"], r["state"], r["due_at"], now),
    )


@router.get("/assignments", response_model=AssignmentPageOut)
def list_assignments(
    q: str | None = Query(default=None, description="Tìm theo mã hồ sơ"),
    assignee: str | None = Query(default=None, description="Mã chuyên viên, hoặc 'unassigned'"),
    status: Literal["unassigned", "in_progress", "needs_info", "due_soon", "overdue", "completed"] | None = Query(
        default=None
    ),
    priority: str | None = Query(default=None),
    source: Literal["manual", "ai_copilot"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    authorization: str | None = Header(default=None),
) -> AssignmentPageOut:
    """Danh sách phân công, có lọc và phân trang.

    Chuyên viên chỉ thấy việc CỦA MÌNH: phạm vi bị ép ở đây, không phụ thuộc
    tham số do trình duyệt gửi lên.
    """
    user = _require(authorization)
    now = datetime.now(UTC)
    own_only = not has_permission(user["role"], Permission.TEAM_WORKLOAD_READ)
    if own_only:
        assignee = user["user_id"]

    where = [f"c.state NOT IN ({_CLOSED})" if status != "completed" else "TRUE"]
    params: dict[str, Any] = {"now": now, "soon": now + DUE_SOON}

    if q:
        where.append("c.case_id ILIKE :q")
        params["q"] = f"%{q}%"
    if assignee == "unassigned":
        where.append("c.assigned_to IS NULL")
    elif assignee:
        where.append("c.assigned_to = :assignee")
        params["assignee"] = assignee
    if priority:
        where.append("c.priority = :priority")
        params["priority"] = priority
    if source:
        where.append("c.assignment_source = :source")
        params["source"] = source

    if status == "unassigned":
        where.append("c.assigned_to IS NULL")
    elif status == "overdue":
        where.append("c.assigned_to IS NOT NULL AND c.due_at IS NOT NULL AND c.due_at < :now")
    elif status == "due_soon":
        where.append("c.assigned_to IS NOT NULL AND c.due_at IS NOT NULL AND c.due_at >= :now AND c.due_at <= :soon")
    elif status == "needs_info":
        where.append("c.assigned_to IS NOT NULL AND c.state = 'DieuTraBoSung'")
    elif status == "in_progress":
        where.append("c.assigned_to IS NOT NULL")
    elif status == "completed":
        where.append(f"c.state IN ({_CLOSED})")

    clause = " AND ".join(where)
    sql = f"""SELECT c.case_id, c.title, c.risk_score, c.priority, c.state, c.assigned_to,
                     c.assigned_at, c.assigned_by, c.assignment_source, c.due_at,
                     u.name AS assignee_name, b.name AS assigned_by_name
                FROM aml_case c
                LEFT JOIN app_user u ON u.user_id = c.assigned_to
                LEFT JOIN app_user b ON b.user_id = c.assigned_by
               WHERE {clause}
               ORDER BY (c.due_at IS NULL), c.due_at ASC, c.risk_score DESC
               LIMIT :limit OFFSET :offset"""
    with get_session() as session:
        total = session.execute(text(f"SELECT count(*) FROM aml_case c WHERE {clause}"), params).scalar_one()
        rows = (
            session.execute(text(sql), {**params, "limit": page_size, "offset": (page - 1) * page_size})
            .mappings()
            .all()
        )
    return AssignmentPageOut(rows=[_row(r, now) for r in rows], total=int(total), page=page, page_size=page_size)


@router.get("/assignments/overview", response_model=OverviewOut)
def assignments_overview(authorization: str | None = Header(default=None)) -> OverviewOut:
    """Số liệu tổng và tải công việc của nhóm.

    Chuyên viên nhận số liệu của CHÍNH MÌNH và một danh sách nhóm rỗng — họ
    không điều phối, và tải việc của đồng nghiệp không phải việc của họ.
    """
    user = _require(authorization)
    now = datetime.now(UTC)
    team = has_permission(user["role"], Permission.TEAM_WORKLOAD_READ)
    scope = "TRUE" if team else "c.assigned_to = :me"
    params: dict[str, Any] = {"now": now, "soon": now + DUE_SOON, "me": user["user_id"]}

    with get_session() as session:
        kpi = (
            session.execute(
                text(
                    f"""SELECT
                        count(*) FILTER (WHERE c.assigned_to IS NULL) AS unassigned,
                        count(*) FILTER (WHERE c.assigned_to IS NOT NULL) AS in_progress,
                        count(*) FILTER (WHERE c.assigned_to IS NOT NULL AND c.due_at IS NOT NULL
                                           AND c.due_at >= :now AND c.due_at <= :soon) AS due_soon,
                        count(*) FILTER (WHERE c.assigned_to IS NOT NULL AND c.due_at IS NOT NULL
                                           AND c.due_at < :now) AS overdue,
                        count(*) FILTER (WHERE c.priority IN ('critical','high')) AS high_priority
                      FROM aml_case c
                     WHERE c.state NOT IN ({_CLOSED}) AND {scope}"""
                ),
                params,
            )
            .mappings()
            .one()
        )
        workload = (
            session.execute(
                text(
                    f"""SELECT u.user_id, u.name,
                               count(c.case_id) FILTER (
                                   WHERE c.state NOT IN ({_CLOSED})) AS open_cases,
                               count(c.case_id) FILTER (
                                   WHERE c.state NOT IN ({_CLOSED})
                                     AND c.priority IN ('critical','high')) AS high_priority,
                               count(c.case_id) FILTER (
                                   WHERE c.state NOT IN ({_CLOSED})
                                     AND c.due_at IS NOT NULL AND c.due_at < :now) AS overdue,
                               count(c.case_id) FILTER (
                                   WHERE c.state NOT IN ({_CLOSED}) AND c.due_at IS NOT NULL
                                     AND c.due_at >= :now AND c.due_at <= :soon) AS due_soon
                          FROM app_user u
                          LEFT JOIN aml_case c ON c.assigned_to = u.user_id
                         WHERE u.role = 'analyst' AND u.active
                         GROUP BY u.user_id, u.name
                         ORDER BY open_cases DESC, u.name"""
                ),
                params,
            )
            .mappings()
            .all()
            if team
            else []
        )

    return OverviewOut(
        can_assign=has_permission(user["role"], Permission.SAR_ASSIGN),
        sees_team=team,
        unassigned=int(kpi["unassigned"]),
        in_progress=int(kpi["in_progress"]),
        due_soon=int(kpi["due_soon"]),
        overdue=int(kpi["overdue"]),
        high_priority=int(kpi["high_priority"]),
        workload=[
            WorkloadRowOut(
                employee_id=w["user_id"],
                name=w["name"],
                open_cases=int(w["open_cases"]),
                high_priority=int(w["high_priority"]),
                overdue=int(w["overdue"]),
                due_soon=int(w["due_soon"]),
            )
            for w in workload
        ],
    )


@router.get("/assignments/{case_id}", response_model=AssignmentDetailOut)
def assignment_detail(case_id: str, authorization: str | None = Header(default=None)) -> AssignmentDetailOut:
    """Chi tiết một hồ sơ kèm LỊCH SỬ phân công.

    Lịch sử dựng từ ``audit_log`` — nguồn bất biến đã có sẵn — chứ không lưu
    thành một bảng riêng có thể lệch với vết kiểm toán.
    """
    user = _require(authorization)
    now = datetime.now(UTC)
    with get_session() as session:
        row = (
            session.execute(
                text(
                    """SELECT c.case_id, c.title, c.risk_score, c.priority, c.state, c.assigned_to,
                              c.assigned_at, c.assigned_by, c.assignment_source, c.due_at,
                              u.name AS assignee_name, b.name AS assigned_by_name
                         FROM aml_case c
                         LEFT JOIN app_user u ON u.user_id = c.assigned_to
                         LEFT JOIN app_user b ON b.user_id = c.assigned_by
                        WHERE c.case_id = :c"""
                ),
                {"c": case_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy hồ sơ {case_id}")
        if not has_permission(user["role"], Permission.TEAM_WORKLOAD_READ) and row["assigned_to"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Hồ sơ này không thuộc phần việc của bạn")

        events = (
            session.execute(
                text(
                    """SELECT l.occurred_at, l.event_type, l.actor, l.payload, u.name AS actor_name
                         FROM audit_log l
                         LEFT JOIN app_user u ON u.user_id = l.actor
                        WHERE l.case_id = :c
                          AND l.event_type IN ('case_assigned', 'case_state_changed', 'alert_raised')
                        ORDER BY l.occurred_at DESC LIMIT 40"""
                ),
                {"c": case_id},
            )
            .mappings()
            .all()
        )
        notes = (
            session.execute(
                text(
                    """SELECT n.body, n.kind, n.created_at, u.name AS author_name
                         FROM case_note n LEFT JOIN app_user u ON u.user_id = n.author
                        WHERE n.case_id = :c ORDER BY n.created_at DESC LIMIT 10"""
                ),
                {"c": case_id},
            )
            .mappings()
            .all()
        )

    names: dict[str, str] = {}
    with get_session() as session:
        names = dict(session.execute(text("SELECT user_id, name FROM app_user")).all())

    return AssignmentDetailOut(
        row=_row(row, now),
        history=[
            {
                "at": e["occurred_at"],
                "event": e["event_type"],
                "actor_name": e["actor_name"],
                "source": (e["payload"] or {}).get("source"),
                "field": (e["payload"] or {}).get("field"),
                "before": _label((e["payload"] or {}).get("before"), names),
                "after": _label((e["payload"] or {}).get("after"), names),
                "reason": (e["payload"] or {}).get("reason"),
            }
            for e in events
        ],
        notes=[
            {"body": n["body"], "kind": n["kind"], "at": n["created_at"], "author_name": n["author_name"]}
            for n in notes
        ],
    )


def _label(value: Any, names: dict[str, str]) -> Any:
    """Mã người dùng trong vết kiểm toán đổi thành họ tên khi hiện ra màn hình."""
    if isinstance(value, str) and value in names:
        return names[value]
    return value


@router.post("/assignments/assign")
def bulk_assign(request: BulkAssignRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Giao một hoặc nhiều hồ sơ cho một chuyên viên.

    Cùng dịch vụ mà trợ lý dùng, nên một lượt giao thủ công và một lượt giao qua
    trò chuyện để lại cùng loại vết và chịu cùng luật.
    """
    user = _require(authorization)
    _guard(user, Permission.SAR_ASSIGN)
    from src.api.routes import _audit_role

    done: list[str] = []
    conflicts: list[dict[str, str]] = []
    with get_session() as session:
        for case_id in request.case_ids:
            try:
                svc.assign(
                    session,
                    case_id=case_id,
                    assignee_id=request.assignee_id,
                    actor=user["user_id"],
                    actor_role=_audit_role(user["role"]),
                    source=svc.Source.MANUAL,
                    reason=request.reason or "Quản lý giao việc",
                )
                if request.due_at:
                    svc.update_deadline(
                        session,
                        case_id=case_id,
                        due_at=request.due_at,
                        actor=user["user_id"],
                        actor_role=_audit_role(user["role"]),
                        source=svc.Source.MANUAL,
                    )
                if request.priority:
                    svc.update_priority(
                        session,
                        case_id=case_id,
                        priority=request.priority,
                        actor=user["user_id"],
                        actor_role=_audit_role(user["role"]),
                        source=svc.Source.MANUAL,
                    )
                if request.instruction:
                    svc.add_note(
                        session,
                        case_id=case_id,
                        body=request.instruction,
                        kind="instruction",
                        actor=user["user_id"],
                        actor_role=_audit_role(user["role"]),
                        source=svc.Source.MANUAL,
                    )
                done.append(case_id)
            except svc.AssignmentError as exc:
                # Một hồ sơ hỏng không được kéo cả lô xuống: báo rõ hồ sơ nào
                # không giao được và vì sao, phần còn lại vẫn đi tiếp.
                conflicts.append({"case_id": case_id, "code": exc.code, "message": exc.message})
    return {"assigned": done, "conflicts": conflicts}


@router.post("/assignments/{case_id}/reassign")
def reassign(
    case_id: str, request: ReassignRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Chuyển một hồ sơ sang chuyên viên khác, có kiểm tranh chấp.

    ``expected_assignee`` là người mà giao diện ĐANG HIỂN THỊ. Lệch với thực tế
    nghĩa là có người vừa động vào; báo lại chứ không ghi đè.
    """
    user = _require(authorization)
    _guard(user, Permission.SAR_REASSIGN)
    from src.api.routes import _audit_role

    with get_session() as session:
        try:
            result = svc.assign(
                session,
                case_id=case_id,
                assignee_id=request.assignee_id,
                actor=user["user_id"],
                actor_role=_audit_role(user["role"]),
                source=svc.Source.MANUAL,
                reason=request.reason,
                expected_assignee=request.expected_assignee,
                check_stale=True,
            )
        except svc.AssignmentError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    return result
