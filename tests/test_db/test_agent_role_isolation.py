"""Vai trò của agent không được chạm tới nhãn.

RD1 là rủi ro mức "Rất cao" trong FIN-07-DAT-001: rò rỉ nhãn vào đặc trưng
cho ra recall gần tuyệt đối và không ai phát hiện cho tới lúc bảo vệ. Triệu
chứng của nó — chỉ số đẹp bất thường — trông giống hệt thành công.

Cách chặn không thể dựa vào kỷ luật viết mã. Nó phải là quyền truy cập:
vai trò `fin07_agent` chỉ đọc được schema `agent`, và schema đó không chứa
cột nhãn nào.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def agent_engine(db_engine):
    """Engine đăng nhập bằng vai trò chỉ đọc của agent."""
    url = db_engine.url.set(
        username="fin07_agent",
        password=os.environ.get("FIN07_AGENT_DB_PASSWORD", "fin07_agent_dev_password"),
    )
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"Không đăng nhập được bằng vai trò fin07_agent: {exc}")
    return engine


def test_agent_can_read_allowed_views(agent_engine):
    with agent_engine.connect() as conn:
        for view in ("transaction", "account", "customer", "alert", "alert_reason", "aml_case"):
            conn.execute(text(f"SELECT * FROM agent.{view} LIMIT 1"))


@pytest.mark.parametrize(
    "table",
    ["label_laundering", "label_typology", "label_profile_mismatch", "label_watchlist_match"],
)
def test_agent_cannot_read_labels(agent_engine, table):
    with pytest.raises(SQLAlchemyError), agent_engine.connect() as conn:
        conn.execute(text(f"SELECT * FROM label.{table} LIMIT 1"))


@pytest.mark.parametrize("table", ["transaction", "audit_log", "evidence", "aml_case"])
def test_agent_cannot_read_base_tables_directly(agent_engine, table):
    """QD1 — agent đi qua bộ công cụ có kiểm soát, không truy vấn bảng gốc."""
    with pytest.raises(SQLAlchemyError), agent_engine.connect() as conn:
        conn.execute(text(f"SELECT * FROM public.{table} LIMIT 1"))


def test_agent_cannot_write(agent_engine):
    with pytest.raises(SQLAlchemyError), agent_engine.connect() as conn:
        conn.execute(
            text("INSERT INTO audit_log (event_type, actor, actor_role) VALUES ('case_viewed', 'agent', 'agent')")
        )
