"""Giữ tài liệu biến môi trường không lạc hậu.

Tiêu chí nghiệm thu của hạng mục hạ tầng có một dòng: "tài liệu biến môi
trường đầy đủ". Một câu như vậy chỉ đúng vào ngày viết ra nó, trừ khi có
thứ gì đó kiểm tra lại mỗi lần. Đây là thứ đó.

Ba nguồn phải khớp nhau:
    src/config.py       — cái mã nguồn thật sự đọc
    .env.example        — cái người mới sao ra để dùng
    docs/ENVIRONMENT.md — cái người ta đọc khi có sự cố

Thêm một trường vào Settings mà quên hai chỗ kia thì bài kiểm thử này đỏ.
"""

import re
from pathlib import Path

import pytest

from src.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
ENV_DOC = (ROOT / "docs" / "ENVIRONMENT.md").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

SETTINGS_FIELDS = sorted(Settings.model_fields)

# Biến chỉ dùng ở tầng compose (không phải trường của Settings): tên image,
# cổng phát ra máy chủ, thông tin khởi tạo container postgres.
COMPOSE_ONLY_VARS = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", COMPOSE)))


@pytest.mark.parametrize("field", SETTINGS_FIELDS)
def test_setting_is_in_env_example(field: str) -> None:
    assert f"{field.upper()}=" in ENV_EXAMPLE, (
        f"Trường Settings.{field} không có trong .env.example. Thêm dòng `{field.upper()}=...` vào đó."
    )


@pytest.mark.parametrize("field", SETTINGS_FIELDS)
def test_setting_is_documented(field: str) -> None:
    assert f"`{field.upper()}`" in ENV_DOC, (
        f"Trường Settings.{field} không có trong docs/ENVIRONMENT.md. Thêm một dòng bảng cho `{field.upper()}`."
    )


@pytest.mark.parametrize("var", COMPOSE_ONLY_VARS)
def test_compose_variable_is_documented(var: str) -> None:
    assert f"`{var}`" in ENV_DOC, f"docker-compose.yml dùng ${{{var}}} nhưng docs/ENVIRONMENT.md không nhắc tới nó."


def test_compose_variables_all_have_defaults() -> None:
    """Máy mới chưa có .env vẫn phải `docker compose up` được.

    Mọi ${BIEN} trong compose phải kèm giá trị mặc định `:-`, nếu không
    compose sẽ thay bằng chuỗi rỗng và dịch vụ lên với cấu hình vô nghĩa.
    """
    without_default = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)\}", COMPOSE)))
    assert not without_default, (
        f"Các biến sau trong docker-compose.yml không có giá trị mặc định: {', '.join(without_default)}"
    )
