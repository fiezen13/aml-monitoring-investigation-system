"""Chính sách của trợ lý điều phối — chốt an toàn thật, không phải lời nhắc.

Mọi bài ở đây chạy trên mã tất định, không gọi mô hình. Đó là chủ ý: nếu an
toàn của hệ thống phụ thuộc vào việc mô hình có nghe lời hay không thì nó không
kiểm chứng được, và cũng không phải an toàn.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.api.copilot.policy import screen_action, screen_case_states
from src.api.copilot.schemas import (
    MAX_CASES_PER_ACTION,
    ActionProposal,
    ActionType,
)

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
CASES = {"CASE-A", "CASE-B", "CASE-C"}
STAFF = {"U-100", "U-101"}


def _proposal(**kw) -> ActionProposal:
    base = {
        "action_id": "ACT-test",
        "action_type": ActionType.ASSIGN_TASK,
        "case_ids": ("CASE-A",),
        "assignee_id": "U-100",
    }
    base.update(kw)
    return ActionProposal(**base)


def _check(proposal: ActionProposal, role: str = "manager"):
    return screen_action(
        proposal,
        trusted_case_ids=CASES,
        trusted_employee_ids=STAFF,
        role=role,
        now=NOW,
    )


# --------------------------------------------------------------------------- #
# Quyền theo VAI TRÒ
# --------------------------------------------------------------------------- #


def test_quan_ly_giao_duoc_viec() -> None:
    assert _check(_proposal()).allowed


@pytest.mark.parametrize("role", ["analyst", "admin"])
def test_chi_quan_ly_moi_giao_duoc_viec(role: str) -> None:
    """Chuyên viên và Quản trị hệ thống đều KHÔNG điều phối được.

    Quản trị hệ thống là thẩm quyền kỹ thuật; nó không mặc nhiên cao hơn Quản lý
    về nghiệp vụ. Nếu ma trận quyền không cấp `sar.assign` thì trợ lý cũng không
    được tự suy ra.
    """
    verdict = _check(_proposal(), role=role)

    assert not verdict.allowed
    assert verdict.code == "missing_permission"


@pytest.mark.parametrize(
    ("action", "expect_allowed"),
    [
        (ActionType.ASSIGN_TASK, True),
        (ActionType.REASSIGN_TASK, True),
        (ActionType.UPDATE_DEADLINE, True),
        (ActionType.UPDATE_PRIORITY, True),
        (ActionType.SEND_REMINDER, True),
        (ActionType.ADD_INSTRUCTION, True),
    ],
)
def test_sau_hanh_dong_dieu_phoi_deu_mo_cho_quan_ly(action: ActionType, expect_allowed: bool) -> None:
    proposal = _proposal(
        action_type=action,
        due_at=NOW + timedelta(hours=6),
        priority="high",
        instruction="Rà soát bổ sung bằng chứng.",
    )

    assert _check(proposal).allowed is expect_allowed


# --------------------------------------------------------------------------- #
# Chống bịa định danh
# --------------------------------------------------------------------------- #


def test_ma_ho_so_khong_co_that_thi_bo_de_xuat() -> None:
    """Mô hình bịa mã hồ sơ là lỗi nguy hiểm nhất: nó giao việc lên một vụ khác."""
    verdict = _check(_proposal(case_ids=("CASE-A", "CASE-KHONG-CO")))

    assert not verdict.allowed
    assert verdict.code == "unknown_case"


def test_nguoi_nhan_khong_co_that_thi_bo_de_xuat() -> None:
    verdict = _check(_proposal(assignee_id="U-999"))

    assert not verdict.allowed
    assert verdict.code == "unknown_assignee"


def test_giao_viec_ma_khong_ro_nguoi_nhan_thi_bo() -> None:
    verdict = _check(_proposal(assignee_id=None))

    assert not verdict.allowed
    assert verdict.code == "no_assignee"


# --------------------------------------------------------------------------- #
# Giới hạn khối lượng và thời gian
# --------------------------------------------------------------------------- #


def test_giao_tat_ca_ho_so_bi_chan_boi_tran_so_luong() -> None:
    """ "Giao tất cả hồ sơ cho Lan" là câu hợp ngữ pháp và mô hình soạn được.

    Không có trần thì một câu nói đổi chủ hàng nghìn vụ việc mà không ai kiểm
    được — trần biến nó thành một lỗi rõ ràng, buộc người dùng thu hẹp yêu cầu.
    """
    qua_nhieu = tuple(f"CASE-{i}" for i in range(MAX_CASES_PER_ACTION + 1))
    verdict = screen_action(
        _proposal(case_ids=qua_nhieu),
        trusted_case_ids=set(qua_nhieu),
        trusted_employee_ids=STAFF,
        role="manager",
        now=NOW,
    )

    assert not verdict.allowed
    assert verdict.code == "too_many_cases"


def test_ho_so_trung_lap_trong_mot_de_xuat_bi_chan() -> None:
    verdict = _check(_proposal(case_ids=("CASE-A", "CASE-A")))

    assert not verdict.allowed
    assert verdict.code == "duplicate_cases"


def test_han_xu_ly_o_qua_khu_bi_chan() -> None:
    verdict = _check(_proposal(due_at=NOW - timedelta(hours=1)))

    assert not verdict.allowed
    assert verdict.code == "deadline_in_past"


def test_han_xu_ly_qua_xa_bi_chan() -> None:
    """Mô hình đọc nhầm năm là lỗi có thật; hạn 2099 phải bị chặn chứ không ghi."""
    verdict = _check(_proposal(due_at=NOW + timedelta(days=400)))

    assert not verdict.allowed
    assert verdict.code == "deadline_too_far"


def test_muc_uu_tien_la_bi_chan() -> None:
    verdict = _check(_proposal(action_type=ActionType.UPDATE_PRIORITY, priority="SIÊU KHẨN"))

    assert not verdict.allowed
    assert verdict.code == "bad_priority"


def test_nhac_viec_khong_co_noi_dung_bi_chan() -> None:
    verdict = _check(_proposal(action_type=ActionType.SEND_REMINDER, instruction=None))

    assert not verdict.allowed
    assert verdict.code == "empty_note"


# --------------------------------------------------------------------------- #
# Kiểm lại trạng thái ở nhịp xác nhận (chống tranh chấp)
# --------------------------------------------------------------------------- #


def test_vu_da_ket_thuc_thi_khong_giao_duoc_nua() -> None:
    cases = [{"case_id": "CASE-A", "state": "XuatHoSo", "assignee_id": None}]

    verdict = screen_case_states(cases, ActionType.ASSIGN_TASK)

    assert not verdict.allowed
    assert verdict.code == "case_closed"


def test_vu_bi_nguoi_khac_nhan_giua_hai_nhip_thi_bao_xung_dot() -> None:
    """Đề xuất soạn lúc vụ còn trống; tới lúc bấm xác nhận thì người khác đã nhận.

    Ghi đè ở đây là âm thầm cướp việc của đồng nghiệp, nên phải báo xung đột.
    """
    cases = [{"case_id": "CASE-A", "state": "TiepNhanCanhBao", "assignee_id": "U-101"}]

    verdict = screen_case_states(cases, ActionType.ASSIGN_TASK)

    assert not verdict.allowed
    assert verdict.code == "case_taken"


def test_chuyen_giao_thi_vu_dang_co_nguoi_la_binh_thuong() -> None:
    """Chuyển giao vốn dĩ tác động lên vụ ĐANG có người — không phải xung đột."""
    cases = [{"case_id": "CASE-A", "state": "TiepNhanCanhBao", "assignee_id": "U-101"}]

    assert screen_case_states(cases, ActionType.REASSIGN_TASK).allowed


# --------------------------------------------------------------------------- #
# Hành động bị cấm không có đường vào
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cam",
    ["APPROVE_SAR", "REJECT_SAR", "CLOSE_CASE", "UPDATE_RISK_SCORE", "GRANT_PERMISSION", "DELETE_CASE"],
)
def test_hanh_dong_tuan_thu_khong_co_trong_danh_sach(cam: str) -> None:
    """Phê duyệt, đóng vụ, sửa điểm rủi ro, đổi quyền — không có công cụ nào.

    Không cần luật chặn riêng: `ActionType` là allowlist, thứ gì không dựng được
    thành `ActionType` thì không có đường thực thi.
    """
    with pytest.raises(ValueError):
        ActionType(cam)
