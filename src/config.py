from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống, nạp từ biến môi trường.

    Mọi biến ở đây phải có mặt trong .env.example và .env.example.
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

    # Google Gemini reasoning layer. `mock` is reserved for CI/development;
    # production agent execution uses the official Google Gen AI SDK.
    llm_mode: Literal["mock", "gemini"] = "mock"
    google_api_key: str = ""
    gemini_model: Literal["gemini-3.1-flash-lite"] = "gemini-3.1-flash-lite"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    gemini_max_retries: int = Field(default=2, ge=0, le=10)

    # Explainable investigation workflow. These are hard safety budgets, not
    # suggestions passed to a model.
    aml_agent_max_iterations: int = Field(default=3, ge=1, le=10)
    aml_agent_max_tool_calls: int = Field(default=8, ge=1, le=50)
    max_graph_hops: int = Field(default=2, ge=1, le=4)
    max_graph_nodes: int = Field(default=100, ge=2, le=1000)
    max_graph_edges: int = Field(default=250, ge=1, le=5000)
    investigation_tx_limit: int = Field(default=100, ge=1, le=500)

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

    @model_validator(mode="after")
    def validate_gemini_runtime(self) -> Self:
        if self.app_env == "production" and self.llm_mode != "gemini":
            raise ValueError("LLM_MODE=gemini is required in production")
        if self.llm_mode != "gemini":
            return self
        if not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required for Gemini agent execution")
        return self

    @property
    def max_agent_iterations(self) -> int:
        """Compatibility name used by the explicit workflow."""
        return self.aml_agent_max_iterations

    @property
    def max_tool_calls(self) -> int:
        """Compatibility name used by the explicit workflow."""
        return self.aml_agent_max_tool_calls


@lru_cache
def get_settings() -> Settings:
    return Settings()
