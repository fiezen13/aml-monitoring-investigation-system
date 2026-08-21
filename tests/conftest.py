import os

# The suite asserts deterministic workflow outcomes, so it must never reach a
# live model whatever LLM_MODE the developer's .env carries. Set before any
# src import, because get_settings() caches on first call.
os.environ["LLM_MODE"] = "mock"

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.api import authz  # noqa: E402
from src.api.authz import enforce_policy  # noqa: E402
from src.main import app  # noqa: E402

#: Người dùng giả cho các test kiểm chứng NỘI DUNG (không có phiên thật). Dùng
#: vai trò phạm vi toàn tổ chức (manager) để các endpoint áp phạm vi cấp-bản-ghi
#: (vd chi tiết vụ việc) không bị chặn — việc kiểm chứng phân quyền nằm riêng ở
#: tests/test_api/test_authz.py với người dùng thật.
_TEST_USER = {
    "user_id": "U-TEST",
    "name": "Test User",
    "email": "test@velrix.vn",
    "role": "manager",
    "role_label": "Quản lý",
    "active": True,
    "last_login": None,
}


@pytest.fixture
def disable_authz():
    """Tắt cổng phân quyền trong phạm vi một test.

    Phần lớn test kiểm chứng *nội dung* endpoint trả về và không có phiên đăng
    nhập thật; bắt xác thực ở đó thì mọi test dừng ở 401 và không còn kiểm
    chứng gì. Bản thân bảng phân quyền được kiểm riêng ở
    ``tests/test_api/test_authz.py`` — file đó cố ý không dùng fixture này.
    """
    app.dependency_overrides[enforce_policy] = lambda: None
    # Một số endpoint còn giải quyết người dùng NGAY TRONG thân hàm để áp phạm vi
    # cấp-bản-ghi (vd get_case gọi _require_user → resolve_user). Cổng đã tắt
    # nhưng phần này vẫn cần một người dùng — cấp một người giả toàn-phạm-vi.
    original_resolve = authz.resolve_user
    # Có token thật (test dùng /auth/login) thì giải quyết THẬT — để các luồng
    # phụ thuộc danh tính (người gửi ≠ người duyệt) vẫn đúng. Không có token mới
    # cấp người dùng giả cho các test chỉ kiểm chứng nội dung.
    authz.resolve_user = lambda authorization=None: (
        original_resolve(authorization) if authorization else dict(_TEST_USER)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(enforce_policy, None)
        authz.resolve_user = original_resolve


@pytest_asyncio.fixture
async def client(disable_authz):
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
