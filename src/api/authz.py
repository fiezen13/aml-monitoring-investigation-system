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

ANALYST = "analyst"  # Chuyên viên
MANAGER = "manager"  # Quản lý (gộp compliance_officer + mlro + auditor cũ)
ADMIN = "admin"  # Quản trị hệ thống

ALL_ROLES = frozenset({ANALYST, MANAGER, ADMIN})

#: HÀNH ĐỘNG điều tra (ghi) và dữ liệu điều tra: khởi chạy điều tra, tài sản mã
#: hoá. Chỉ Chuyên viên và Quản lý — quản trị hệ thống (admin) không đọc hồ sơ
#: khách hàng, không ra quyết định AML.
INVESTIGATION = frozenset({ANALYST, MANAGER})

#: XEM dữ liệu điều tra — cảnh báo, vụ việc, đồ thị, giao dịch. Sau khi gộp vai
#: trò, người xem cũng chính là người điều tra (Chuyên viên + Quản lý); không còn
#: vai trò "chỉ đọc" tách riêng.
INVESTIGATION_READ = INVESTIGATION

#: Tab KỸ THUẬT: chất lượng dữ liệu, đánh giá chuẩn, giám sát mô hình, lượt chạy
#: tác tử. Theo yêu cầu sản phẩm — CHỈ ADMIN. Chuyên viên và Quản lý đều KHÔNG thấy.
MODEL_QUALITY = frozenset({ADMIN})

#: ĐỌC hồ sơ SAR (xem danh sách, xem chi tiết, xuất bản đã duyệt, hỏi trợ lý).
#: Cả hai vai: Quản lý phải đọc được hồ sơ mới phê duyệt được nó.
SAR_READ = frozenset({ANALYST, MANAGER})

#: SOẠN/SỬA/KIỂM CHỨNG/NỘP hồ sơ SAR — CHỈ Chuyên viên.
#:
#: Phân tách nhiệm vụ: người lập hồ sơ và người chốt hồ sơ phải khác VAI, không
#: chỉ khác người. Trước đây Quản lý cũng soạn và nộp được, nên một Quản lý đã
#: tự trình một hồ sơ rồi thấy nó trong hàng đợi chờ chính mình duyệt — chốt
#: "người gửi không tự phê duyệt" chặn được cá nhân đó, nhưng vụ việc thì kẹt
#: và quy trình mất ý nghĩa.
SAR_PREPARE = frozenset({ANALYST})

#: Nhật ký kiểm toán nghiệp vụ — Quản lý giám sát, Admin xem dấu vết hệ thống.
AUDIT = frozenset({MANAGER, ADMIN})

# Quản trị người dùng/hệ thống là THẨM QUYỀN KỸ THUẬT — chỉ ADMIN (khớp
# MANAGE_USERS/MANAGE_SYSTEM = admin trong src/api/permissions.py).
USER_ADMIN = frozenset({ADMIN})
SETTINGS = frozenset({ADMIN})

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
    # --- Cảnh báo --- (Chuyên viên + Quản lý; quản trị hệ thống không đọc)
    "/alerts": INVESTIGATION_READ,
    "/alerts/page": INVESTIGATION_READ,
    "/alerts/{alert_id}": INVESTIGATION_READ,
    "/alerts/{alert_id}/investigate": INVESTIGATION,
    "/alerts/{alert_id}/investigation": INVESTIGATION_READ,
    # --- Vụ việc --- (Chuyên viên + Quản lý; quản trị hệ thống không đọc)
    "/cases": INVESTIGATION_READ,
    "/cases/page": INVESTIGATION_READ,
    "/cases/{case_id}": INVESTIGATION_READ,
    "/cases/{case_id}/network": INVESTIGATION_READ,
    "/cases/{case_id}/sar": SAR_PREPARE,
    "/cases/{case_id}/assign": INVESTIGATION,
    # Bảng nhân sự "ai đang gánh bao nhiêu" là công cụ CHIA VIỆC — thẩm quyền
    # của Quản lý. Chuyên viên xem số liệu việc của chính mình qua "/my-work".
    "/workload": frozenset({MANAGER}),
    "/my-work": INVESTIGATION_READ,
    # Xác nhận / huỷ một đề xuất của trợ lý điều phối. Cổng ở đây chỉ chặn theo
    # vai; QUYỀN cho từng loại hành động được kiểm lại trong `copilot.policy`,
    # vì một endpoint phục vụ sáu hành động có mức thẩm quyền khác nhau.
    "/actions/{action_id}/confirm": INVESTIGATION,
    "/actions/{action_id}/cancel": INVESTIGATION,
    # --- Phiên điều tra của tác tử ---
    "/investigations/{investigation_id}": INVESTIGATION_READ,
    "/investigations/{investigation_id}/evidence": INVESTIGATION_READ,
    "/investigations/{investigation_id}/trace": INVESTIGATION_READ,
    "/investigations/{investigation_id}/explanation": INVESTIGATION_READ,
    "/investigations/{investigation_id}/package": INVESTIGATION_READ,
    # KẾT LUẬN điều tra là việc của CHUYÊN VIÊN (quản lý chốt ở tầng phê duyệt).
    # Cổng này còn sót lại từ mô hình cũ "quản lý vừa kết luận vừa duyệt": thân
    # hàm đã mở cho analyst nhưng cổng vẫn chặn, nên chuyên viên không đẩy được
    # vụ nào sang Soạn hồ sơ nghi vấn — cả quy trình hai vai bị kẹt ngay bước một.
    # Kết luận về một phiên điều tra là bước NGHIỆP VỤ của Chuyên viên; nó
    # đẩy vụ sang "Soạn hồ sơ nghi vấn" hoặc sinh đề nghị đóng vụ. Quản lý
    # chốt ở "/approvals/{approval_id}/decision", không kết luận thay.
    "/investigations/{investigation_id}/review": frozenset({ANALYST}),
    # Nhãn rà soát: vòng phản hồi của Quản lý (giám sát nghiệp vụ) và Admin (theo
    # dõi chất lượng mô hình). Chuyên viên không tham gia gắn nhãn.
    "/feedback/labels": AUDIT,
    # --- Hồ sơ SAR và phê duyệt ---
    "/sars": SAR_READ,
    # Hàng đợi ĐỀ NGHỊ ĐÓNG VỤ. Cùng chính sách với SAR: chuyên viên nộp đề
    # nghị, quản lý chốt bằng "/approvals/{approval_id}/decision".
    "/approvals/close-requests": SAR_READ,
    # Trợ lý AI hỏi–đáp về hàng đợi SAR — chỉ đọc/tư vấn, cùng quyền xem SAR.
    "/sars/ai-chat": SAR_READ,
    "/sars/{sar_id}": SAR_READ,
    "/sars/{sar_id}/narrative": SAR_PREPARE,
    "/sars/{sar_id}/preparer": SAR_PREPARE,
    "/sars/{sar_id}/validate": SAR_PREPARE,
    "/sars/{sar_id}/submit": SAR_PREPARE,
    "/sars/{sar_id}/export": SAR_READ,
    # Màn hình "Phê duyệt SAR" dựng từ /sars — bảng `approval` đi kèm mỗi hồ sơ
    # trong payload đó. Không có endpoint danh sách riêng và cũng không cần.
    # Quyết định phê duyệt hồ sơ rủi ro cao là THẨM QUYỀN NGHIỆP VỤ AML — chỉ
    # Quản lý. Admin (quản trị hệ thống) không ra quyết định AML (khớp APPROVE_CASE/
    # DECIDE_SAR = manager trong permissions.py).
    "/approvals/{approval_id}/decision": frozenset({MANAGER}),
    # --- Tra cứu giao dịch ---
    "/transactions": INVESTIGATION_READ,
    # --- Đồ thị và tài sản mã hoá ---
    # Đồ thị là dữ liệu điều tra — Chuyên viên + Quản lý, khớp VIEW_ENTITY_GRAPH.
    "/fc/graph": INVESTIGATION_READ,
    # Cùng quyền với /fc/graph: nó đọc chính bằng chứng của bộ dò đồ thị cho các
    # tài khoản đang hiển thị, không mở thêm dữ liệu nào. Thiếu dòng này thì bảng
    # chính sách mặc-định-đóng chặn mọi vai trò và tab Chu trình luôn báo 401.
    "/fc/graph/patterns": INVESTIGATION_READ,
    # Bản kể của tác tử cho vùng đồ thị: đọc đúng những giao dịch mà /fc/graph
    # đã vẽ, chỉ diễn đạt lại, nên cùng quyền xem đồ thị.
    "/fc/graph/narrative": INVESTIGATION_READ,
    "/fc/graph/edges/{edge_id}/transactions": INVESTIGATION_READ,
    "/fc/graph/nodes/{node_id}/transactions": INVESTIGATION_READ,
    "/fc/crypto": INVESTIGATION,
    # Giải thích Gemini on-demand cho một giao dịch Bitcoin — cùng quyền điều tra.
    "/fc/bitcoin/{tx_id}/explain": INVESTIGATION,
    "/fc/bitcoin": INVESTIGATION_READ,
    # --- Tác tử AI ---
    "/fc/agent-runs": MODEL_QUALITY,
    "/fc/agent-runs/{run_id}": MODEL_QUALITY,
    # --- Chất lượng và mô hình ---
    "/fc/benchmarks": MODEL_QUALITY,
    # Đối chiếu nhiều nhánh, mỗi nhánh benchmark trên vùng của nó. Cùng quyền
    # với /fc/benchmarks: đây là dữ liệu chất lượng mô hình.
    "/fc/model-branches": MODEL_QUALITY,
    "/fc/model-monitor": MODEL_QUALITY,
    "/fc/edge-model/release": MODEL_QUALITY,
    "/fc/data-quality": MODEL_QUALITY,
    "/fc/observations": MODEL_QUALITY,
    "/fc/sources": MODEL_QUALITY,
    # --- Quản trị ---
    "/audit": AUDIT,
    "/audit/by-case": AUDIT,
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
