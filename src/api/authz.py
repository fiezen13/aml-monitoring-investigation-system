"""Phân quyền theo vai trò ở tầng API.

Ẩn mục menu chỉ là tiện dụng: ai biết đường dẫn vẫn gọi thẳng được API. Nên
quyết định "vai trò nào gọi được endpoint nào" phải nằm ở đây, và giao diện chỉ
phản chiếu lại nó.

Cách áp dụng là một dependency ở cấp router (xem ``src/main.py``) chứ không phải
sửa chữ ký của năm chục hàm endpoint. Đổi lại, bảng chính sách bên dưới phải
liệt kê **đủ** đường dẫn: bất kỳ route nào không có trong bảng đều bị từ chối
(mặc định đóng). Thêm endpoint mới mà quên khai báo thì nó trả 403 ngay lần gọi
đầu — ồn ào và sửa được, thay vì lặng lẽ mở toang.

Khớp theo ``request.scope["route"].path`` — tức khuôn đường dẫn còn nguyên tham
số (``/alerts/{alert_id}``), không phải URL đã điền giá trị. Nhờ vậy không có
chuyện một mã cảnh báo lạ làm lệch việc so khớp.

Khoá trong bảng viết **không kèm** tiền tố ``/api/v1``: FastAPI 0.141 gắn router
con như một mount, nên ``route.path`` là đường dẫn tương đối trong router. Các
bản cũ hơn lại trả về đường dẫn đầy đủ, nên ``_policy_key`` cắt tiền tố nếu có —
nâng cấp thư viện không được phép âm thầm mở toang chính sách.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import Header, HTTPException, Request
from sqlalchemy import text

from src.db.session import get_session

ANALYST = "analyst"
COMPLIANCE = "compliance_officer"
MLRO = "mlro"
AUDITOR = "auditor"
ADMIN = "admin"

ALL_ROLES = frozenset({ANALYST, COMPLIANCE, MLRO, AUDITOR, ADMIN})

#: Công việc điều tra hằng ngày: xem cảnh báo, vụ việc, đồ thị, tài sản mã hoá.
#: Cố ý không có ``auditor`` — kiểm toán viên rà lại quyết định đã ra chứ không
#: tham gia ra quyết định; và không có ``admin`` — quản trị hạ tầng không cần
#: đọc hồ sơ khách hàng.
INVESTIGATION = frozenset({ANALYST, COMPLIANCE, MLRO})

#: Dữ liệu điều tra ở chế độ chỉ đọc — kiểm toán viên được xem để đối chiếu.
INVESTIGATION_READ = INVESTIGATION | {AUDITOR}

#: Chất lượng dữ liệu, đánh giá chuẩn, giám sát mô hình. Analyst không cần.
MODEL_QUALITY = frozenset({COMPLIANCE, MLRO, AUDITOR, ADMIN})

#: Hồ sơ SAR và phê duyệt — chỉ người ký chịu trách nhiệm.
SAR = frozenset({COMPLIANCE, MLRO})

#: Nhật ký kiểm toán — mọi vai trò giám sát, trừ analyst.
AUDIT = frozenset({COMPLIANCE, MLRO, AUDITOR, ADMIN})

USER_ADMIN = frozenset({ADMIN, COMPLIANCE})
SETTINGS = frozenset({ADMIN, MLRO})

#: Route ai cũng gọi được, kể cả khi chưa đăng nhập.
PUBLIC: frozenset[str] = frozenset(
    {
        "/auth/users",
        "/auth/login",
        # CẢNH BÁO: điểm nạp alert của nhánh ML hiện không xác thực. Nó phải
        # được chặn ở tầng mạng (chỉ cho phép trong VPC). Đây là khoảng trống
        # đã biết, giữ nguyên để không phá hợp đồng với pipeline ngoài.
        "/internal/alerts",
    }
)

#: Bảng chính sách: khuôn đường dẫn -> tập vai trò được phép.
#:
#: Chỉ phân quyền theo *đường dẫn*, không theo phương thức. Kiểm tra chi tiết
#: hơn (ví dụ "người gửi không được tự phê duyệt hồ sơ của mình") vẫn nằm trong
#: từng endpoint, vì nó phụ thuộc dữ liệu chứ không phụ thuộc vai trò.
POLICY: dict[str, frozenset[str]] = {
    # --- Phiên làm việc: ai đăng nhập được thì cũng tự xem và tự thoát được ---
    "/auth/me": ALL_ROLES,
    "/auth/logout": ALL_ROLES,
    # --- Giám sát tổng quan: số liệu tổng hợp, không lộ hồ sơ cá nhân ---
    "/dashboard": ALL_ROLES,
    "/world": ALL_ROLES,
    "/nav-counts": ALL_ROLES,
    "/queue": ALL_ROLES,
    "/status": ALL_ROLES,
    "/search": INVESTIGATION_READ,
    # --- Cảnh báo ---
    "/alerts": INVESTIGATION,
    "/alerts/page": INVESTIGATION,
    "/alerts/{alert_id}": INVESTIGATION,
    "/alerts/{alert_id}/investigate": INVESTIGATION,
    "/alerts/{alert_id}/investigation": INVESTIGATION_READ,
    # --- Vụ việc ---
    "/cases": INVESTIGATION,
    "/cases/{case_id}": INVESTIGATION,
    "/cases/{case_id}/investigate": INVESTIGATION,
    "/cases/{case_id}/network": INVESTIGATION,
    "/cases/{case_id}/sar": SAR,
    # --- Phiên điều tra của tác tử ---
    "/investigations/{investigation_id}": INVESTIGATION_READ,
    "/investigations/{investigation_id}/evidence": INVESTIGATION_READ,
    "/investigations/{investigation_id}/trace": INVESTIGATION_READ,
    "/investigations/{investigation_id}/explanation": INVESTIGATION_READ,
    "/investigations/{investigation_id}/package": INVESTIGATION_READ,
    "/investigations/{investigation_id}/review": frozenset({COMPLIANCE, MLRO}),
    "/feedback/labels": MODEL_QUALITY,
    # --- Hồ sơ SAR và phê duyệt ---
    "/sars": SAR,
    "/sars/{sar_id}": SAR,
    "/sars/{sar_id}/validate": SAR,
    "/sars/{sar_id}/submit": SAR,
    "/sars/{sar_id}/export": SAR,
    # Màn hình "Phê duyệt SAR" dựng từ /sars — bảng `approval` đi kèm mỗi hồ sơ
    # trong payload đó. Không có endpoint danh sách riêng và cũng không cần.
    "/approvals/{approval_id}/decision": frozenset({MLRO, ADMIN}),
    # --- Tra cứu giao dịch ---
    "/transactions": INVESTIGATION_READ,
    # --- Đồ thị và tài sản mã hoá ---
    "/fc/graph": INVESTIGATION,
    # Cùng quyền với /fc/graph: nó đọc chính bằng chứng của bộ dò đồ thị cho các
    # tài khoản đang hiển thị, không mở thêm dữ liệu nào. Thiếu dòng này thì bảng
    # chính sách mặc-định-đóng chặn mọi vai trò và tab Chu trình luôn báo 401.
    "/fc/graph/patterns": INVESTIGATION,
    # Bản kể của tác tử cho vùng đồ thị: đọc đúng những giao dịch mà /fc/graph
    # đã vẽ, chỉ diễn đạt lại, nên cùng quyền điều tra.
    "/fc/graph/narrative": INVESTIGATION,
    "/fc/graph/edges/{edge_id}/transactions": INVESTIGATION,
    "/fc/graph/nodes/{node_id}/transactions": INVESTIGATION,
    "/fc/crypto": INVESTIGATION,
    "/fc/projects": INVESTIGATION,
    # --- Tác tử AI ---
    "/fc/agent-runs": INVESTIGATION_READ,
    "/fc/agent-runs/{run_id}": INVESTIGATION_READ,
    # --- Chất lượng và mô hình ---
    "/fc/benchmarks": MODEL_QUALITY,
    # Đối chiếu nhiều nhánh, mỗi nhánh benchmark trên vùng của nó. Cùng quyền
    # với /fc/benchmarks: đây là dữ liệu chất lượng mô hình.
    "/fc/model-branches": MODEL_QUALITY,
    # --- Nhánh Bitcoin AML (Elliptic++) ---
    # Suy luận là công việc điều tra: cùng quyền với đọc cảnh báo/đồ thị.
    "/aml/bitcoin/predict": INVESTIGATION,
    "/aml/bitcoin/predict/batch": INVESTIGATION,
    "/fc/model-monitor": MODEL_QUALITY,
    "/fc/edge-model/release": MODEL_QUALITY,
    "/fc/data-quality": MODEL_QUALITY,
    "/fc/observations": MODEL_QUALITY,
    "/fc/sources": MODEL_QUALITY,
    # --- Quản trị ---
    "/audit": AUDIT,
    "/users": USER_ADMIN,
    "/users/{user_id}": USER_ADMIN,
    "/settings": SETTINGS,
    "/settings/{code}": SETTINGS,
}


def resolve_user(authorization: str | None) -> dict[str, Any]:
    """Đổi Bearer token lấy bản ghi người dùng, hoặc ném 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không tồn tại")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with get_session() as session:
        row = (
            session.execute(
                text(
                    """SELECT u.user_id, u.name, u.email, u.role, u.role_label, u.active, u.last_login
                         FROM app_session s JOIN app_user u ON u.user_id = s.user_id
                        WHERE s.token_hash = :token_hash AND s.expires_at > now() AND u.active"""
                ),
                {"token_hash": token_hash},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn")
    return dict(row)


#: Tiền tố mà ``src/main.py`` gắn router vào. Chỉ dùng để chuẩn hoá khoá tra cứu.
_API_PREFIX = "/api/v1"


def _policy_key(path: str) -> str:
    """Chuẩn hoá đường dẫn route về đúng dạng khoá trong ``POLICY``."""
    if path.startswith(_API_PREFIX):
        return path[len(_API_PREFIX) :] or "/"
    return path


def allowed_paths(role: str) -> list[str]:
    """Danh sách endpoint một vai trò gọi được — dùng cho kiểm thử và chẩn đoán."""
    return sorted(path for path, roles in POLICY.items() if role in roles)


async def enforce_policy(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Dependency cấp router: chặn trước khi endpoint chạy.

    Bỏ qua CORS preflight — trình duyệt gửi OPTIONS *không kèm* header
    Authorization, nên bắt xác thực ở đó sẽ chặn mọi request chéo gốc.
    """
    if request.method == "OPTIONS":
        return

    route = request.scope.get("route")
    raw_path = getattr(route, "path", None)
    if raw_path is None:
        return
    path = _policy_key(raw_path)
    if path in PUBLIC:
        return

    user = resolve_user(authorization)
    allowed = POLICY.get(path)
    if allowed is None:
        # Mặc định đóng. Endpoint mới chưa khai báo chính sách thì không ai gọi
        # được — kể cả admin — cho tới khi có người quyết định nó thuộc về ai.
        raise HTTPException(
            status_code=403,
            detail="Endpoint chưa được khai báo chính sách phân quyền",
        )
    if user["role"] not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Vai trò '{user['role_label']}' không được truy cập chức năng này",
        )
