"""Kiểm chính sách cho đề xuất hành động — chốt an toàn thật của trợ lý.

Lời nhắc hệ thống là lớp TRẢI NGHIỆM: nó khiến mô hình hành xử đúng phần lớn
thời gian. Nó không phải biên giới an ninh, vì nó chỉ là văn bản và mô hình có
thể bị dẫn đi chệch. Biên giới nằm ở đây — mã tất định, chạy trên máy chủ, và
chạy HAI LẦN: một lần lúc soạn đề xuất, một lần nữa lúc người dùng xác nhận.

Chạy lại lúc xác nhận không phải là thừa. Giữa hai nhịp đó, vụ việc có thể đã
được người khác nhận, chuyên viên có thể đã bị khoá tài khoản, và quyền của
người bấm nút có thể đã bị thu hồi.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.api.copilot.schemas import (
    ACTION_PERMISSION,
    CLOSED_CASE_STATES,
    MAX_CASES_PER_ACTION,
    MAX_DEADLINE_HORIZON,
    NEEDS_ASSIGNEE,
    PRIORITIES,
    ActionProposal,
    ActionType,
    PolicyVerdict,
)
from src.api.permissions import permissions_for

OK = PolicyVerdict(allowed=True)


def _deny(code: str, message: str) -> PolicyVerdict:
    return PolicyVerdict(allowed=False, code=code, message=message)


def screen_action(
    proposal: ActionProposal,
    *,
    trusted_case_ids: set[str],
    trusted_employee_ids: set[str],
    role: str,
    now: datetime,
) -> PolicyVerdict:
    """Kiểm một đề xuất trước khi nó được lưu hoặc được thực thi.

    ``trusted_case_ids``/``trusted_employee_ids`` là những định danh CÓ THẬT mà
    máy chủ vừa truy vấn. Mô hình nhắc tới thứ gì ngoài hai tập đó thì đề xuất
    bị bỏ — đây là phép chống bịa định danh rẻ nhất mà vẫn chặn được đúng loại
    lỗi nguy hiểm nhất.
    """
    action = proposal.action_type
    if action not in ACTION_PERMISSION:
        return _deny("unknown_action", "Trợ lý không hỗ trợ thao tác này.")

    granted = permissions_for(role)
    needed = ACTION_PERMISSION[action]
    if needed not in granted:
        return _deny(
            "missing_permission",
            "Tài khoản của bạn không có quyền thực hiện thao tác điều phối này.",
        )

    if not proposal.case_ids:
        return _deny("no_target", "Chưa xác định được hồ sơ nào để thực hiện. Bạn nêu rõ mã hồ sơ giúp mình.")

    if len(proposal.case_ids) > MAX_CASES_PER_ACTION:
        return _deny(
            "too_many_cases",
            f"Một lần chỉ xử lý tối đa {MAX_CASES_PER_ACTION} hồ sơ. Bạn thu hẹp yêu cầu lại "
            "(ví dụ theo mức rủi ro hoặc theo nhóm hồ sơ cụ thể) rồi thử lại nhé.",
        )

    if len(set(proposal.case_ids)) != len(proposal.case_ids):
        return _deny("duplicate_cases", "Danh sách hồ sơ bị trùng lặp, mình chưa thực hiện.")

    unknown = [c for c in proposal.case_ids if c not in trusted_case_ids]
    if unknown:
        return _deny(
            "unknown_case",
            "Có mã hồ sơ không tìm thấy trong dữ liệu hiện tại, nên mình không đề xuất thao tác. "
            "Bạn kiểm tra lại mã hồ sơ giúp mình.",
        )

    if action in NEEDS_ASSIGNEE:
        if not proposal.assignee_id:
            return _deny("no_assignee", "Chưa rõ giao cho ai. Bạn nêu tên chuyên viên giúp mình.")
        if proposal.assignee_id not in trusted_employee_ids:
            return _deny(
                "unknown_assignee",
                "Không tìm thấy chuyên viên này trong danh sách đang hoạt động. Bạn kiểm tra lại tên nhé.",
            )

    if proposal.priority is not None and proposal.priority not in PRIORITIES:
        return _deny("bad_priority", "Mức ưu tiên không hợp lệ.")

    if proposal.due_at is not None:
        if proposal.due_at <= now:
            return _deny("deadline_in_past", "Hạn xử lý đang ở quá khứ. Bạn nêu lại mốc thời gian giúp mình.")
        if proposal.due_at - now > MAX_DEADLINE_HORIZON:
            return _deny(
                "deadline_too_far",
                f"Hạn xử lý xa hơn {MAX_DEADLINE_HORIZON.days} ngày, nhiều khả năng đã hiểu nhầm mốc thời "
                "gian. Bạn nêu lại ngày giờ cụ thể giúp mình.",
            )

    if action in {ActionType.SEND_REMINDER, ActionType.ADD_INSTRUCTION} and not (proposal.instruction or "").strip():
        return _deny("empty_note", "Chưa có nội dung nhắc việc hoặc chỉ dẫn để gửi.")

    if action == ActionType.UPDATE_PRIORITY and not proposal.priority:
        return _deny("no_priority", "Chưa rõ đổi sang mức ưu tiên nào.")

    if action == ActionType.UPDATE_DEADLINE and proposal.due_at is None:
        return _deny("no_deadline", "Chưa rõ hạn xử lý mới là khi nào.")

    return OK


def screen_case_states(cases: list[dict[str, Any]], action: ActionType) -> PolicyVerdict:
    """Trạng thái vụ việc có còn cho phép thao tác không.

    Chạy ở nhịp xác nhận với dữ liệu vừa đọc lại: vụ đã kết thúc trong lúc người
    dùng còn đang đọc thẻ xác nhận thì thao tác không còn nghĩa.
    """
    closed = [c["case_id"] for c in cases if c["state"] in CLOSED_CASE_STATES]
    if closed:
        return _deny(
            "case_closed",
            "Có hồ sơ đã kết thúc nên không giao việc được nữa. Bạn xem lại danh sách rồi thử lại nhé.",
        )
    if action == ActionType.ASSIGN_TASK:
        taken = [c["case_id"] for c in cases if c.get("assignee_id")]
        if taken:
            return _deny(
                "case_taken",
                "Trong lúc bạn xem, có hồ sơ đã được người khác nhận. Mình không ghi đè; "
                "bạn xem lại danh sách rồi giao lại phần còn thiếu nhé.",
            )
    return OK
