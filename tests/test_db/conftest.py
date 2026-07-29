import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine


@pytest.fixture(scope="session")
def db_engine():
    """Engine tới PostgreSQL, bỏ qua cả nhóm nếu không nối được.

    Chạy `docker compose up -d postgres` là các bài kiểm thử này chạy. Trong
    CI, service container luôn có nên chúng luôn chạy — không có chuyện bài
    kiểm thử tự lặng lẽ bỏ qua ở nơi lẽ ra nó phải chạy.
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")
    return engine
