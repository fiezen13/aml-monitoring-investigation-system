"""Kiểu dữ liệu của màn "Phân công & tải công việc".

Trạng thái trả về là MÃ nghiệp vụ (``overdue``, ``due_soon``…), không phải câu
tiếng Việt: giao diện đổi cách gọi mà không phải sửa máy chủ, và hai màn hình
cùng đọc một mã thì không thể gọi tên khác nhau.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

#: Trạng thái nghiệp vụ của một dòng phân công. Suy tại thời điểm hỏi, không lưu.
AssignmentStatus = Literal[
    "unassigned", "in_progress", "needs_info", "due_soon", "overdue", "completed"
]


class AssignmentRowOut(BaseModel):
    case_id: str
    title: str | None = None
    risk_score: float
    priority: str
    state: str
    assignee_id: str | None = None
    assignee_name: str | None = None
    assigned_at: datetime | None = None
    #: Người BẤM NÚT giao việc — kể cả khi phương án do trợ lý soạn. Trùng với
    #: `assignee_id` nghĩa là chuyên viên TỰ NHẬN, không ai giao cho họ cả.
    assigned_by_id: str | None = None
    assigned_by_name: str | None = None
    #: 'manual' | 'ai_copilot' | None (chưa giao).
    source: str | None = None
    due_at: datetime | None = None
    status: AssignmentStatus


class AssignmentPageOut(BaseModel):
    rows: list[AssignmentRowOut]
    total: int
    page: int
    page_size: int


class WorkloadRowOut(BaseModel):
    employee_id: str
    name: str
    open_cases: int
    high_priority: int
    overdue: int
    due_soon: int


class OverviewOut(BaseModel):
    """Số liệu tổng. ``can_assign``/``sees_team`` do MÁY CHỦ quyết định.

    Giao diện dùng hai cờ này để ẩn nút và ẩn bảng nhân sự, nhưng đó chỉ là tiện
    dụng — mọi endpoint ghi vẫn tự kiểm quyền.
    """

    can_assign: bool
    sees_team: bool
    unassigned: int
    in_progress: int
    due_soon: int
    overdue: int
    high_priority: int
    workload: list[WorkloadRowOut] = Field(default_factory=list)


class AssignmentDetailOut(BaseModel):
    row: AssignmentRowOut
    history: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)


class BulkAssignRequest(BaseModel):
    #: Trần 50 hồ sơ một lượt — cùng tinh thần với trần của trợ lý: một thao tác
    #: không ai soát được thì không nên thực hiện được bằng một cú bấm.
    case_ids: list[str] = Field(..., min_length=1, max_length=50)
    assignee_id: str
    priority: str | None = None
    due_at: datetime | None = None
    instruction: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=500)


class ReassignRequest(BaseModel):
    assignee_id: str
    reason: str = Field(..., min_length=3, max_length=500)
    #: Người mà giao diện đang hiển thị; lệch thì máy chủ báo xung đột.
    expected_assignee: str | None = None
