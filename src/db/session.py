"""Kết nối PostgreSQL dùng chung cho API, worker và script vận hành."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Engine dùng chung, kèm hai hàng rào chống một kết nối làm kẹt cả hệ thống.

    ``idle_in_transaction_session_timeout``: một tiến trình bị giết giữa chừng —
    container bị dừng, mạng đứt, người vận hành bấm Ctrl-C — để lại kết nối treo
    *trong* transaction. PostgreSQL không biết client đã chết và giữ nguyên mọi
    khoá dòng nó đang nắm. Quy trình điều tra khoá dòng ``alert`` bằng
    ``SELECT ... FOR UPDATE``, nên một kết nối mồ côi khoá vĩnh viễn cảnh báo đó:
    người dùng bấm "Điều tra" và màn hình đứng ở "đang chờ" mãi mãi, không có lỗi
    nào để đọc. Đã gặp đúng tình huống này trên môi trường thật.

    ``lock_timeout``: khi vẫn có tranh chấp khoá, thà hỏng nhanh và nói rõ còn
    hơn treo im lặng — 30 giây đủ cho một phiên điều tra bình thường nhả khoá.

    Cố ý **không** đặt ``statement_timeout``: các script chạy theo lô có những
    truy vấn quét cả bảng hàng phút, và cắt ngang chúng thì hỏng việc thật.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_pre_ping=True,
        future=True,
        connect_args={
            "options": "-c idle_in_transaction_session_timeout=120000 -c lock_timeout=30000",
        },
    )


@lru_cache
def _get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """True nếu cơ sở dữ liệu trả lời được một truy vấn tầm thường."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
