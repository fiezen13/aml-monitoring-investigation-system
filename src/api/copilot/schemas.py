"""Kiểu dữ liệu cho trợ lý điều phối — biên giới giữa mô hình và cơ sở dữ liệu.

Mô hình ngôn ngữ không bao giờ chạm vào cơ sở dữ liệu. Nó chỉ được sinh ra một
``ActionProposal``: một cấu trúc đóng, mọi trường đều có kiểu, và mọi định danh
trong đó còn phải đối chiếu lại với dữ liệu thật trước khi được coi là hợp lệ.

Chia hai nhịp là điểm mấu chốt:

* **PREPARE** — mô hình đề xuất, máy chủ đối chiếu và lưu tham số bất biến.
* **EXECUTE** — người thật xác nhận, máy chủ đọc lại tham số ĐÃ LƯU và thực thi
  bằng mã tất định. Không đọc lại câu tiếng Việt, không tin thân yêu cầu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from src.api.permissions import Permission


class ActionType(str, Enum):  # noqa: UP042 — giữ str Enum cho Python 3.10
    """Toàn bộ hành động ghi mà trợ lý được phép ĐỀ XUẤT.

    Danh sách này là allowlist: thứ gì không có ở đây thì không có đường thực
    thi, kể cả khi mô hình có bịa ra tên hành động. Cố ý KHÔNG có phê duyệt/từ
    chối hồ sơ, đóng vụ, sửa điểm rủi ro hay đổi quyền — những quyết định đó chỉ
    đi qua màn hình nghiệp vụ chính thức.
    """

    ASSIGN_TASK = "ASSIGN_TASK"
    REASSIGN_TASK = "REASSIGN_TASK"
    UPDATE_DEADLINE = "UPDATE_DEADLINE"
    UPDATE_PRIORITY = "UPDATE_PRIORITY"
    SEND_REMINDER = "SEND_REMINDER"
    ADD_INSTRUCTION = "ADD_INSTRUCTION"


#: Quyền bắt buộc cho từng hành động. Chính sách kiểm theo BẢNG NÀY, không kiểm
#: theo chuỗi vai trò — vai trò đổi được, còn bảng này nói rõ ai làm được gì.
ACTION_PERMISSION: dict[ActionType, Permission] = {
    ActionType.ASSIGN_TASK: Permission.SAR_ASSIGN,
    ActionType.REASSIGN_TASK: Permission.SAR_REASSIGN,
    ActionType.UPDATE_DEADLINE: Permission.TASK_DEADLINE_UPDATE,
    ActionType.UPDATE_PRIORITY: Permission.TASK_PRIORITY_UPDATE,
    ActionType.SEND_REMINDER: Permission.TASK_REMIND,
    ActionType.ADD_INSTRUCTION: Permission.TASK_REMIND,
}

#: Hành động cần có người nhận việc.
NEEDS_ASSIGNEE = frozenset({ActionType.ASSIGN_TASK, ActionType.REASSIGN_TASK})

#: Mức ưu tiên nghiệp vụ — đúng các giá trị `aml_case.priority` đang dùng.
PRIORITIES = ("critical", "high", "medium", "low")

#: Trần số hồ sơ một đề xuất được đụng tới.
#:
#: "Giao tất cả hồ sơ cho Lan" là một câu hợp ngữ pháp và mô hình sẽ soạn được
#: đề xuất cho cả 14 nghìn vụ. Trần này biến một thao tác không ai kiểm được
#: thành một lỗi rõ ràng, buộc người dùng thu hẹp yêu cầu.
MAX_CASES_PER_ACTION = 20

#: Đề xuất sống bao lâu trước khi phải soạn lại.
PROPOSAL_TTL = timedelta(minutes=15)

#: Hạn xử lý xa nhất chấp nhận được — chặn "hạn 2099" do mô hình đọc nhầm năm.
MAX_DEADLINE_HORIZON = timedelta(days=90)

#: Trạng thái vụ việc KHÔNG còn giao việc được nữa.
CLOSED_CASE_STATES = ("XuatHoSo", "DongKhongBaoCao")


@dataclass(frozen=True)
class ActionProposal:
    """Một đề xuất hành động đã được đối chiếu với dữ liệu thật.

    ``requires_confirmation`` luôn True: không có đường nào để trợ lý thực thi
    thẳng. Giữ trường này trong cấu trúc (thay vì ngầm hiểu) để giao diện đọc
    được ý định ấy mà không cần biết luật của máy chủ.
    """

    action_id: str
    action_type: ActionType
    case_ids: tuple[str, ...] = ()
    #: Ảnh chụp hồ sơ để dựng thẻ xác nhận: mã, tiêu đề, rủi ro, ưu tiên.
    cases: tuple[dict[str, Any], ...] = ()
    assignee_id: str | None = None
    assignee_display_name: str | None = None
    #: Khối lượng việc HIỆN CÓ của người nhận, để người duyệt thấy mình đang
    #: chất thêm lên ai. None khi chưa đo được — giao diện bỏ trống chứ không đoán.
    assignee_workload: dict[str, int] | None = None
    #: Người đang giữ vụ, chỉ có nghĩa với REASSIGN_TASK.
    current_assignee_name: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    instruction: str | None = None
    reason: str = ""
    requires_confirmation: bool = True

    def to_payload(self) -> dict[str, Any]:
        """Tham số BẤT BIẾN đem lưu. Đây là nguồn sự thật lúc thực thi."""
        return {
            "action_type": self.action_type.value,
            "case_ids": list(self.case_ids),
            "assignee_id": self.assignee_id,
            "priority": self.priority,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "instruction": self.instruction,
        }

    def to_card(self) -> dict[str, Any]:
        """Dữ liệu để giao diện dựng thẻ xác nhận.

        Trả về cấu trúc, KHÔNG trả Markdown: nút bấm giả bằng chữ thì người dùng
        không phân biệt được đâu là hành động thật.
        """
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "case_ids": list(self.case_ids),
            "cases": [dict(c) for c in self.cases],
            "assignee_id": self.assignee_id,
            "assignee_display_name": self.assignee_display_name,
            "assignee_workload": self.assignee_workload,
            "current_assignee_name": self.current_assignee_name,
            "priority": self.priority,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "instruction": self.instruction,
            "reason": self.reason,
            "requires_confirmation": True,
        }


@dataclass(frozen=True)
class PolicyVerdict:
    """Kết quả kiểm chính sách cho một đề xuất."""

    allowed: bool
    #: Mã lý do để ghi nhật ký; câu chữ cho người dùng nằm ở ``message``.
    code: str = ""
    #: Câu giải thích bằng ngôn ngữ nghiệp vụ, hiện thẳng lên màn hình.
    message: str = ""


@dataclass
class CopilotReply:
    """Câu trả lời của trợ lý điều phối.

    Một lượt hoặc là TRẢ LỜI (``answer``), hoặc là ĐỀ XUẤT kèm câu dẫn. Không
    bao giờ là "đã làm xong" — chỉ endpoint thực thi mới nói được câu đó.
    """

    answer: str
    proposal: ActionProposal | None = None
    blocked: bool = False
    category: str = ""
    detail: str = ""
    #: Ghi chú chính sách khi một đề xuất bị từ chối, để ghi vào nhật ký.
    policy: PolicyVerdict | None = None
    grounded_on: dict[str, Any] = field(default_factory=dict)


def utcnow() -> datetime:
    return datetime.now(UTC)
