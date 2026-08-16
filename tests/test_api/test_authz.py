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
        ("auditor", "/api/v1/alerts"),  # kiểm toán viên không vào hàng đợi cảnh báo
        ("admin", "/api/v1/cases"),  # quản trị hạ tầng không đọc hồ sơ điều tra
        ("analyst", "/api/v1/users"),  # analyst không quản trị người dùng
        ("analyst", "/api/v1/settings"),
        ("analyst", "/api/v1/audit"),
        ("analyst", "/api/v1/fc/benchmarks"),
    ],
)
async def test_vai_tro_bi_chan(raw_client, as_role, role: str, path: str) -> None:
    as_role(role)
    response = await raw_client.get(path, headers={"Authorization": "Bearer x"})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["analyst", "auditor", "compliance_officer"])
async def test_chi_mlro_va_admin_ra_quyet_dinh_phe_duyet(raw_client, as_role, role: str) -> None:
    """Chặn ngay ở cổng, trước cả khi đọc thân yêu cầu."""
    as_role(role)
    response = await raw_client.post(
        "/api/v1/approvals/APR-1/decision",
        headers={"Authorization": "Bearer x"},
        json={},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "path"),
    [
        ("analyst", "/api/v1/alerts"),
        ("mlro", "/api/v1/alerts"),
        ("auditor", "/api/v1/audit"),
        ("auditor", "/api/v1/transactions"),
        ("admin", "/api/v1/users"),
        ("compliance_officer", "/api/v1/users"),
        ("mlro", "/api/v1/settings"),
        ("auditor", "/api/v1/fc/data-quality"),
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
