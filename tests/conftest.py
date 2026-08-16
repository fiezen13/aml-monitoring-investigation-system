import os

# The suite asserts deterministic workflow outcomes, so it must never reach a
# live model whatever LLM_MODE the developer's .env carries. Set before any
# src import, because get_settings() caches on first call.
os.environ["LLM_MODE"] = "mock"

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.api.authz import enforce_policy  # noqa: E402
from src.main import app  # noqa: E402


@pytest.fixture
def disable_authz():
    """Tắt cổng phân quyền trong phạm vi một test.

    Phần lớn test kiểm chứng *nội dung* endpoint trả về và không có phiên đăng
    nhập thật; bắt xác thực ở đó thì mọi test dừng ở 401 và không còn kiểm
    chứng gì. Bản thân bảng phân quyền được kiểm riêng ở
    ``tests/test_api/test_authz.py`` — file đó cố ý không dùng fixture này.
    """
    app.dependency_overrides[enforce_policy] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(enforce_policy, None)


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
