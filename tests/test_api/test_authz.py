"""Kiểm chứng bảng phân quyền ở tầng API.

Không dùng fixture ``client`` của conftest — fixture đó cố tình tắt phân quyền
để các test khác kiểm chứng nội dung. Ở đây thì phân quyền chính là thứ cần đo,
nên dựng client riêng và chỉ giả lập bước đổi token lấy người dùng.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api import authz
from src.main import app


@pytest_asyncio.fixture
async def raw_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def as_role(monkeypatch):
    """Đăng nhập giả với một vai trò, không chạm cơ sở dữ liệu."""

    def _apply(role: str) -> None:
        def _resolve(authorization: str | None) -> dict[str, object]:
            if not authorization:
                raise authz.HTTPException(status_code=401, detail="Phiên đăng nhập không tồn tại")
            return {"user_id": "U-TEST", "role": role, "role_label": role, "active": True}

        monkeypatch.setattr(authz, "resolve_user", _resolve)

    return _apply


def test_moi_route_deu_co_chinh_sach() -> None:
    """Không endpoint nào dưới /api/v1 được phép thiếu khai báo.

    Đây là lưới an toàn quan trọng nhất của module: quên khai báo nghĩa là
    endpoint mới rơi vào nhánh "mặc định đóng" và trả 403 cho tất cả — test này
    bắt được lỗi đó ngay khi thêm route, thay vì để người dùng phát hiện.
    """
    paths = {authz._policy_key(p) for p in app.openapi()["paths"] if p.startswith("/api/v1")}
    thieu = sorted(p for p in paths if p not in authz.POLICY and p not in authz.PUBLIC)
    assert thieu == [], f"Các route chưa khai báo phân quyền: {thieu}"


def test_khong_co_chinh_sach_thua() -> None:
    """Khoá trỏ vào endpoint không tồn tại là dấu hiệu bảng đã lệch khỏi code."""
    paths = {authz._policy_key(p) for p in app.openapi()["paths"] if p.startswith("/api/v1")}
    thua = sorted(p for p in authz.POLICY if p not in paths)
    assert thua == [], f"Chính sách trỏ tới route không còn tồn tại: {thua}"


@pytest.mark.asyncio
async def test_thieu_token_bi_tu_choi(raw_client) -> None:
    response = await raw_client.get("/api/v1/alerts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dang_nhap_va_health_khong_can_token(raw_client) -> None:
    """Hai đường này phải mở, nếu không thì không ai đăng nhập được."""
    assert (await raw_client.get("/health")).status_code == 200
    # /auth/users chạm DB nên có thể lỗi 500 ở môi trường không có DB; điều cần
    # khẳng định là nó *không* bị chặn ở 401/403.
    assert (await raw_client.get("/api/v1/auth/users")).status_code not in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "path"),
    [
        ("admin", "/api/v1/alerts"),  # quản trị hạ tầng không đọc cảnh báo
        ("admin", "/api/v1/cases"),  # quản trị hạ tầng không đọc hồ sơ điều tra
        ("analyst", "/api/v1/users"),  # analyst không quản trị người dùng
        ("analyst", "/api/v1/settings"),
        ("analyst", "/api/v1/audit"),
        # Tab KỸ THUẬT chỉ dành cho ADMIN — Chuyên viên VÀ Quản lý đều bị chặn.
        ("analyst", "/api/v1/fc/benchmarks"),
        ("analyst", "/api/v1/fc/agent-runs"),
        ("analyst", "/api/v1/fc/data-quality"),
        ("manager", "/api/v1/fc/benchmarks"),
        ("manager", "/api/v1/fc/agent-runs"),
        ("manager", "/api/v1/fc/data-quality"),
        ("manager", "/api/v1/fc/model-monitor"),
        # Quản trị user/hệ thống là thẩm quyền KỸ THUẬT — chỉ ADMIN.
        ("manager", "/api/v1/users"),
        ("manager", "/api/v1/settings"),
        # Bảng nhân sự "ai đang gánh bao nhiêu" là công cụ CHIA VIỆC. Chuyên
        # viên không phân công cho ai, và không cần thấy khối lượng việc của
        # đồng nghiệp; số liệu của chính mình lấy ở "/my-work".
        ("analyst", "/api/v1/workload"),
        ("admin", "/api/v1/workload"),
    ],
)
async def test_vai_tro_bi_chan(raw_client, as_role, role: str, path: str) -> None:
    as_role(role)
    response = await raw_client.get(path, headers={"Authorization": "Bearer x"})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["analyst", "admin"])
async def test_chi_quan_ly_ra_quyet_dinh_phe_duyet(raw_client, as_role, role: str) -> None:
    """Quyết định phê duyệt là thẩm quyền NGHIỆP VỤ AML — chỉ Quản lý.

    Chuyên viên chưa đủ thẩm quyền; Admin (quản trị hệ thống) không ra quyết định
    AML. Chặn ngay ở cổng, trước cả khi đọc thân yêu cầu.
    """
    as_role(role)
    response = await raw_client.post(
        "/api/v1/approvals/APR-1/decision",
        headers={"Authorization": "Bearer x"},
        json={},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
# "/cases/{id}/investigate" đã gỡ 27/08/2026 cùng chuỗi trạng thái trung gian.
@pytest.mark.parametrize("path", ["/api/v1/alerts/A-1/investigate"])
async def test_admin_khong_duoc_dieu_tra(raw_client, as_role, path: str) -> None:
    """Admin (quản trị hệ thống) KHÔNG khởi chạy điều tra — không đọc hồ sơ khách hàng."""
    as_role("admin")
    response = await raw_client.post(path, headers={"Authorization": "Bearer x"}, json={})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "path"),
    [
        # Chuyên viên + Quản lý làm nghiệp vụ điều tra.
        ("analyst", "/api/v1/alerts"),
        ("analyst", "/api/v1/cases"),
        ("analyst", "/api/v1/fc/graph"),
        ("analyst", "/api/v1/transactions"),
        ("manager", "/api/v1/alerts"),
        ("manager", "/api/v1/cases"),
        ("manager", "/api/v1/fc/graph"),
        ("manager", "/api/v1/transactions"),
        ("manager", "/api/v1/audit"),  # Quản lý xem nhật ký kiểm toán nghiệp vụ
        # Admin: quản trị hệ thống + toàn bộ tab kỹ thuật.
        ("admin", "/api/v1/users"),
        ("admin", "/api/v1/settings"),
        ("admin", "/api/v1/audit"),
        ("admin", "/api/v1/fc/data-quality"),
        ("admin", "/api/v1/fc/benchmarks"),
        ("admin", "/api/v1/fc/agent-runs"),
        # Số liệu công việc của CHÍNH mình: cả hai vai nghiệp vụ đều cần.
        ("analyst", "/api/v1/my-work"),
        ("manager", "/api/v1/my-work"),
        ("manager", "/api/v1/workload"),
        # Quản lý vẫn phải ĐỌC được hồ sơ và xuất bản đã duyệt — không đọc được
        # thì không phê duyệt được.
        ("manager", "/api/v1/sars"),
        ("manager", "/api/v1/approvals/close-requests"),
    ],
)
async def test_vai_tro_duoc_qua_cong(raw_client, as_role, role: str, path: str) -> None:
    """Qua được cổng phân quyền; nội dung trả về là việc của test khác.

    Không khẳng định 200 vì các endpoint này đều chạm cơ sở dữ liệu — điều cần
    khẳng định là chúng không bị 401/403 chặn lại.
    """
    as_role(role)
    response = await raw_client.get(path, headers={"Authorization": "Bearer x"})
    assert response.status_code not in (401, 403), response.text


def test_chuyen_vien_duoc_ghi_ket_luan_dieu_tra() -> None:
    """Cổng phân quyền phải cho CHUYÊN VIÊN ghi kết luận điều tra.

    Quy trình hai vai đặt việc kết luận ở chuyên viên và việc chốt ở quản lý.
    Cổng này từng sót lại `{MANAGER}` của mô hình cũ trong khi thân hàm đã mở cho
    analyst: chuyên viên bị 403, không vụ nào sang được "Soạn hồ sơ nghi vấn",
    và cả quy trình kẹt ngay bước đầu (phát hiện khi chạy thử luồng trên
    production 2026-08-27).
    """
    from src.api.authz import POLICY

    assert "analyst" in POLICY["/investigations/{investigation_id}/review"]
    # Quyết định PHÊ DUYỆT thì ngược lại: chỉ quản lý.
    assert "analyst" not in POLICY["/approvals/{approval_id}/decision"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        # PHÂN TÁCH NHIỆM VỤ: Quản lý CHỐT hồ sơ, không lập hồ sơ. Cho họ soạn
        # thì người phê duyệt và người lập là cùng một VAI, và nguyên tắc bốn
        # mắt chỉ còn chặn được đúng cá nhân đó chứ không chặn được vai trò —
        # đã xảy ra thật: một Quản lý trình hồ sơ rồi thấy nó trong hàng đợi
        # chờ chính mình duyệt.
        ("POST", "/api/v1/cases/CASE-X/sar"),
        ("PUT", "/api/v1/sars/SAR-X/narrative"),
        ("PUT", "/api/v1/sars/SAR-X/preparer"),
        ("POST", "/api/v1/sars/SAR-X/validate"),
        ("POST", "/api/v1/sars/SAR-X/submit"),
        # Kết luận một phiên điều tra cũng là bước của Chuyên viên: nó đẩy vụ
        # sang "Soạn hồ sơ nghi vấn" hoặc sinh đề nghị đóng vụ.
        ("POST", "/api/v1/investigations/INV-X/review"),
    ],
)
async def test_quan_ly_khong_lap_ho_so(raw_client, as_role, method: str, path: str) -> None:
    """Quản lý chỉ chốt, không soạn/nộp hồ sơ.

    Dùng ĐÚNG phương thức của route: các đường này chỉ nhận POST/PUT, gọi bằng
    GET thì nhận 405 và test sẽ xanh vì lý do sai.
    """
    as_role("manager")
    response = await raw_client.request(method, path, headers={"Authorization": "Bearer x"}, json={})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/cases/CASE-X/sar"),
        ("POST", "/api/v1/sars/SAR-X/validate"),
        ("POST", "/api/v1/sars/SAR-X/submit"),
        ("POST", "/api/v1/investigations/INV-X/review"),
    ],
)
async def test_chuyen_vien_van_lap_duoc_ho_so(raw_client, as_role, method: str, path: str) -> None:
    """Mặt còn lại của cùng một luật: siết Quản lý mà chặn nhầm Chuyên viên thì
    không ai lập được hồ sơ nữa."""
    as_role("analyst")
    response = await raw_client.request(method, path, headers={"Authorization": "Bearer x"}, json={})
    assert response.status_code not in (401, 403), response.text
