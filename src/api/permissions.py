"""Mô hình phân quyền tập trung — nguồn sự thật DUY NHẤT cho RBAC.

BA vai trò (theo yêu cầu sản phẩm): tách bạch NGHIỆP VỤ khỏi KỸ THUẬT.
  * ``analyst`` — Chuyên viên: rà soát cảnh báo, điều tra, dòng tiền, vụ việc.
    KHÔNG thấy nội dung kỹ thuật/mô hình.
  * ``manager`` — Quản lý: mọi việc của Chuyên viên + soạn/duyệt SAR + phê duyệt
    + nhật ký kiểm toán nghiệp vụ + giám sát công việc. Vẫn KHÔNG thấy tab kỹ
    thuật (đánh giá chuẩn / giám sát mô hình / chất lượng dữ liệu / lượt chạy tác tử).
  * ``admin`` — Quản trị hệ thống: TẤT CẢ tab kỹ thuật + người dùng + cấu hình.
    KHÔNG ra quyết định AML (không cảnh báo/vụ việc/phê duyệt).

Nguyên tắc: quyền chỉ theo ``user.role`` (không theo tên/email/nhãn); mặc định
TỪ CHỐI; chỉ khai báo quyền cho năng lực CÓ THẬT. "Tab kỹ thuật = chỉ Admin".
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):  # noqa: UP042 — giữ str Enum cho Python 3.10
    ANALYST = "analyst"  # Chuyên viên
    MANAGER = "manager"  # Quản lý (gộp compliance + mlro + auditor cũ)
    ADMIN = "admin"  # Quản trị hệ thống


class DataScope(str, Enum):  # noqa: UP042 — giữ str Enum cho Python 3.10
    """Phạm vi bản ghi một vai trò được đọc."""

    ASSIGNED = "assigned"  # chỉ hồ sơ được giao cho mình
    ALL = "all"  # toàn tổ chức (đọc–ghi theo quyền)
    READ_ONLY_ALL = "read_only_all"  # toàn tổ chức chỉ đọc (giữ để tương thích)
    SYSTEM = "system"  # dữ liệu quản trị hệ thống (admin)


class Permission(str, Enum):  # noqa: UP042 — giữ str Enum cho Python 3.10
    # Bảng điều khiển
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_EXECUTIVE_DASHBOARD = "view_executive_dashboard"  # Quản lý
    VIEW_SYSTEM_DASHBOARD = "view_system_dashboard"  # Admin
    VIEW_AUDIT_DASHBOARD = "view_audit_dashboard"  # (giữ cho tương thích)
    # Cảnh báo
    VIEW_ALERTS = "view_alerts"
    INVESTIGATE_ALERT = "investigate_alert"
    # Vụ việc
    VIEW_CASES = "view_cases"
    INVESTIGATE_CASE = "investigate_case"
    ESCALATE_CASE = "escalate_case"
    APPROVE_CASE = "approve_case"  # quyết định rủi ro cao — Quản lý
    # SAR/STR
    PREPARE_SAR = "prepare_sar"  # Quản lý soạn
    DECIDE_SAR = "decide_sar"  # Quản lý quyết định/nộp
    # Tra cứu & đồ thị
    VIEW_TRANSACTIONS = "view_transactions"
    VIEW_ENTITY_GRAPH = "view_entity_graph"
    VIEW_CRYPTO = "view_crypto"
    # Giải thích mô hình / tác tử (nghiệp vụ)
    VIEW_INVESTIGATION = "view_investigation"
    REVIEW_INVESTIGATION = "review_investigation"
    VIEW_MODEL_EXPLAIN = "view_model_explain"
    # Chất lượng & giám sát mô hình (KỸ THUẬT — chỉ Admin)
    VIEW_MODEL_QUALITY = "view_model_quality"
    VIEW_MODEL_GOVERNANCE = "view_model_governance"
    # Báo cáo
    VIEW_REPORTS = "view_reports"
    EXPORT_REPORT = "export_report"
    # Kiểm toán
    VIEW_AUDIT_LOG = "view_audit_log"
    # Quản trị hệ thống
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    MANAGE_SYSTEM = "manage_system"


P = Permission

#: Quyền của từng vai trò. "Tab kỹ thuật" (VIEW_MODEL_QUALITY/GOVERNANCE) chỉ
#: thuộc ADMIN — Chuyên viên và Quản lý đều KHÔNG có.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ANALYST: frozenset(
        {
            P.VIEW_DASHBOARD,
            P.VIEW_ALERTS,
            P.INVESTIGATE_ALERT,
            P.VIEW_CASES,
            P.INVESTIGATE_CASE,
            P.ESCALATE_CASE,
            P.PREPARE_SAR,  # Chuyên viên soạn & nộp SAR; Quản lý mới phê duyệt.
            P.VIEW_TRANSACTIONS,
            P.VIEW_ENTITY_GRAPH,
            P.VIEW_CRYPTO,
            P.VIEW_INVESTIGATION,
            P.VIEW_MODEL_EXPLAIN,
            P.VIEW_REPORTS,
        }
    ),
    Role.MANAGER: frozenset(
        {
            P.VIEW_DASHBOARD,
            P.VIEW_EXECUTIVE_DASHBOARD,
            P.VIEW_ALERTS,
            P.INVESTIGATE_ALERT,
            P.VIEW_CASES,
            P.INVESTIGATE_CASE,
            P.ESCALATE_CASE,
            P.APPROVE_CASE,
            # KHÔNG có PREPARE_SAR. Quản lý CHỐT, không soạn: cho họ soạn thì
            # cùng một người vừa lập hồ sơ vừa nằm trong nhóm phê duyệt, và
            # nguyên tắc bốn mắt chỉ còn chặn được đúng cá nhân đó chứ không
            # chặn được vai trò. Đã xảy ra thật trên production — một Quản lý
            # trình hồ sơ rồi thấy chính nó trong hàng đợi chờ mình duyệt.
            P.DECIDE_SAR,
            P.VIEW_TRANSACTIONS,
            P.VIEW_ENTITY_GRAPH,
            P.VIEW_CRYPTO,
            P.VIEW_INVESTIGATION,
            P.REVIEW_INVESTIGATION,
            P.VIEW_MODEL_EXPLAIN,
            P.VIEW_REPORTS,
            P.EXPORT_REPORT,
            P.VIEW_AUDIT_LOG,
            # KHÔNG có VIEW_MODEL_QUALITY / VIEW_MODEL_GOVERNANCE — tab kỹ thuật = admin.
        }
    ),
    Role.ADMIN: frozenset(
        {
            P.VIEW_DASHBOARD,
            P.VIEW_SYSTEM_DASHBOARD,
            P.VIEW_MODEL_QUALITY,
            P.VIEW_MODEL_GOVERNANCE,  # toàn bộ tab kỹ thuật
            P.VIEW_AUDIT_LOG,
            P.VIEW_REPORTS,
            P.MANAGE_USERS,
            P.MANAGE_ROLES,
            P.MANAGE_SYSTEM,
            # KHÔNG có quyền nghiệp vụ AML (cảnh báo/vụ việc/phê duyệt/SAR).
        }
    ),
}

#: Phạm vi dữ liệu mặc định của mỗi vai trò.
#
# ANALYST = ALL: chuyên viên thấy CẢ hàng đợi vụ việc, nhất quán với việc họ đã
# thấy mọi cảnh báo để phân loại. Trước đây là ASSIGNED (chỉ vụ được giao) nhưng
# hệ thống chưa có luồng giao việc → mọi vụ việc đều assigned_to=NULL nên chuyên
# viên thấy TRỐNG, trông như hỏng. Quyền GHI vẫn do permission_codes kiểm soát
# riêng, không phải data-scope, nên mở phạm vi đọc không nới quyền hành động.
ROLE_DATA_SCOPE: dict[Role, DataScope] = {
    Role.ANALYST: DataScope.ALL,
    Role.MANAGER: DataScope.ALL,
    Role.ADMIN: DataScope.SYSTEM,
}


def _role(role: str) -> Role | None:
    try:
        return Role(role)
    except ValueError:
        return None


def permissions_for(role: str) -> frozenset[Permission]:
    """Quyền của một vai trò. Vai trò lạ → RỖNG (mặc định từ chối)."""
    r = _role(role)
    return ROLE_PERMISSIONS.get(r, frozenset()) if r else frozenset()


def has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for(role)


def data_scope_for(role: str) -> DataScope:
    """Phạm vi dữ liệu của vai trò. Vai trò lạ → ASSIGNED (hẹp nhất)."""
    r = _role(role)
    return ROLE_DATA_SCOPE.get(r, DataScope.ASSIGNED) if r else DataScope.ASSIGNED


def permission_codes(role: str) -> list[str]:
    """Danh sách mã quyền (chuỗi) để trả cho ``/auth/me`` và frontend."""
    return sorted(p.value for p in permissions_for(role))


def scope_own_records(role: str) -> bool:
    """True nếu vai trò chỉ được thấy bản ghi ĐƯỢC GIAO (analyst)."""
    return data_scope_for(role) == DataScope.ASSIGNED
