from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống, nạp từ biến môi trường.

    Mọi biến ở đây phải có mặt trong .env.example và docs/ENVIRONMENT.md.
    Kiểm thử tests/test_config.py khẳng định điều đó, nên thêm một trường
    mà quên tài liệu thì CI đỏ.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "FIN-07 AML Agent"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:5173"

    # LLM
    openai_api_key: str = ""
    google_api_key: str = ""
    model_name: str = "gemini-1.5-flash"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database
    database_url: str = "postgresql+psycopg://fin07:fin07_dev_password@localhost:5432/fin07"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_pool_max_overflow: int = Field(default=5, ge=0, le=50)

    # Redis / hàng đợi tác vụ
    redis_url: str = "redis://localhost:6379/0"
    worker_queue: str = "fin07:jobs"
    worker_poll_interval: float = Field(default=1.0, gt=0, le=60)
    # Nhịp tim worker ghi vào Redis; healthcheck của container đọc khoá này.
    worker_heartbeat_key: str = "fin07:worker:heartbeat"
    worker_heartbeat_ttl: int = Field(default=30, ge=5, le=600)

    # Dữ liệu mẫu
    seed_value: int = 20260728
    seed_customers: int = Field(default=48, ge=4, le=5000)
    seed_days: int = Field(default=90, ge=7, le=730)

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()
