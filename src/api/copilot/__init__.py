"""Trợ lý điều phối nghiệp vụ AML (AML Operations Copilot).

Kiến trúc một chiều, mỗi nhịp một trách nhiệm::

    câu tiếng Việt
      → agent      (mô hình chọn hành động trong danh sách đóng)
      → tools      (máy chủ truy vấn lại dữ liệu thật, đối chiếu định danh)
      → policy     (kiểm quyền và giới hạn — chốt an toàn thật)
      → store      (giữ tham số bất biến, chờ người thật xác nhận)
      → tools      (thực thi tất định)
      → audit_log

Mô hình không sinh SQL, không gọi ORM, và không có đường nào để câu chữ của nó
trở thành một phép ghi. Nó chỉ điền tham số cho một hành động đã được định
nghĩa sẵn; mọi thứ sau đó là mã tất định.
"""

from src.api.copilot import agent, policy, store, tools
from src.api.copilot.schemas import (
    ACTION_PERMISSION,
    MAX_CASES_PER_ACTION,
    ActionProposal,
    ActionType,
    CopilotReply,
    PolicyVerdict,
)

__all__ = [
    "ACTION_PERMISSION",
    "MAX_CASES_PER_ACTION",
    "ActionProposal",
    "ActionType",
    "CopilotReply",
    "PolicyVerdict",
    "agent",
    "policy",
    "store",
    "tools",
]
