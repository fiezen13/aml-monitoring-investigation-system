"""Kiểm chứng mô hình phân quyền tập trung (src/api/permissions.py).

Bổ sung cho test_authz.py (kiểm ở tầng route): ở đây kiểm THẲNG bảng quyền và
phạm vi dữ liệu của BA vai trò — Chuyên viên (analyst), Quản lý (manager), Quản
trị hệ thống (admin) — mặc định từ chối, tách bạch nghiệp vụ khỏi kỹ thuật.
"""

from __future__ import annotations

import pytest

from src.api.permissions import (
    DataScope,
    Permission,
    data_scope_for,
    has_permission,
    permission_codes,
    scope_own_records,
)

P = Permission


def test_vai_tro_la_tu_choi_toan_bo() -> None:
    """Vai trò không xác định → không có quyền nào (mặc định đóng)."""
    assert permission_codes("hacker") == []
    assert not has_permission("", P.VIEW_ALERTS)
    assert data_scope_for("hacker") == DataScope.ASSIGNED  # hẹp nhất


@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        # Chuyên viên: điều tra được, KHÔNG duyệt/SAR/quản trị/kỹ thuật.
        ("analyst", P.INVESTIGATE_ALERT, True),
        ("analyst", P.ESCALATE_CASE, True),
        ("analyst", P.APPROVE_CASE, False),
        ("analyst", P.DECIDE_SAR, False),
        ("analyst", P.MANAGE_USERS, False),
        ("analyst", P.VIEW_MODEL_QUALITY, False),  # tab kỹ thuật = admin
        ("analyst", P.VIEW_AUDIT_LOG, False),
        # Quản lý: toàn quyền nghiệp vụ AML — soạn + quyết định SAR + phê duyệt +
        # nhật ký kiểm toán. Nhưng KHÔNG tab kỹ thuật, KHÔNG quản trị hệ thống.
        # PHÂN TÁCH NHIỆM VỤ: Quản lý CHỐT hồ sơ, không lập hồ sơ. Người phê
        # duyệt và người lập phải khác VAI, không chỉ khác người — nếu cùng vai
        # thì nguyên tắc bốn mắt chỉ chặn được đúng cá nhân đó.
        ("manager", P.PREPARE_SAR, False),
        ("manager", P.DECIDE_SAR, True),
        ("manager", P.APPROVE_CASE, True),
        ("manager", P.INVESTIGATE_ALERT, True),
        ("manager", P.VIEW_AUDIT_LOG, True),
        ("manager", P.EXPORT_REPORT, True),
        ("manager", P.VIEW_MODEL_QUALITY, False),  # tab kỹ thuật = admin
        ("manager", P.MANAGE_USERS, False),  # nghiệp vụ ≠ kỹ thuật
        ("manager", P.MANAGE_SYSTEM, False),
        # Admin: quản trị hệ thống + toàn bộ tab kỹ thuật, KHÔNG ra quyết định AML.
        ("admin", P.MANAGE_USERS, True),
        ("admin", P.MANAGE_SYSTEM, True),
        ("admin", P.VIEW_MODEL_QUALITY, True),
        ("admin", P.VIEW_MODEL_GOVERNANCE, True),
        ("admin", P.INVESTIGATE_ALERT, False),
        ("admin", P.APPROVE_CASE, False),
        ("admin", P.PREPARE_SAR, False),
        ("admin", P.VIEW_ALERTS, False),
    ],
)
def test_ma_tran_quyen(role: str, permission: Permission, expected: bool) -> None:
    assert has_permission(role, permission) is expected


def test_admin_khong_ra_quyet_dinh_aml() -> None:
    """Quản trị hệ thống không chạm nghiệp vụ AML (điều tra/duyệt/SAR/cảnh báo)."""
    aml_perms = {
        P.VIEW_ALERTS,
        P.INVESTIGATE_ALERT,
        P.INVESTIGATE_CASE,
        P.ESCALATE_CASE,
        P.APPROVE_CASE,
        P.PREPARE_SAR,
        P.DECIDE_SAR,
    }
    for perm in aml_perms:
        assert not has_permission("admin", perm), f"admin không được có {perm}"


def test_tab_ky_thuat_chi_admin() -> None:
    """Tab kỹ thuật (chất lượng/giám sát mô hình) chỉ Admin — cả hai vai trò
    nghiệp vụ đều KHÔNG thấy."""
    for perm in (P.VIEW_MODEL_QUALITY, P.VIEW_MODEL_GOVERNANCE):
        assert not has_permission("analyst", perm)
        assert not has_permission("manager", perm)
        assert has_permission("admin", perm)


def test_pham_vi_du_lieu() -> None:
    # analyst = ALL, KHÔNG phải ASSIGNED: hệ thống chưa có luồng giao việc nên
    # mọi vụ việc đều assigned_to=NULL, để ASSIGNED thì chuyên viên mở hàng đợi
    # ra thấy trống và tưởng hỏng. Quyền GHI vẫn do permission_codes chặn riêng
    # nên nới phạm vi ĐỌC không nới quyền hành động. Xem ROLE_DATA_SCOPE.
    # Khi nào có luồng giao việc thì đổi lại ASSIGNED cùng lúc ở cả hai nơi.
    assert data_scope_for("analyst") == DataScope.ALL
    assert scope_own_records("analyst") is False
    assert data_scope_for("manager") == DataScope.ALL
    assert scope_own_records("manager") is False
    assert data_scope_for("admin") == DataScope.SYSTEM
    assert scope_own_records("admin") is False
