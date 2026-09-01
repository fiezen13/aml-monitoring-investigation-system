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
    log_format: Literal["json", "text"] = "json"
    cors_origins: str = "http://localhost:5173"

    # OpenTelemetry. Disabled by default so `docker compose up` remains
    # independent from the optional observability profile.
    otel_enabled: bool = False
    otel_service_name: str = "fin07-backend"
    otel_service_version: str = "1.0.0"
    otel_service_instance_id: str = ""
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_exporter_otlp_protocol: Literal["grpc", "http/protobuf"] = "grpc"
    otel_resource_attributes: str = ""
    otel_traces_sampler: Literal["always_on", "always_off", "parentbased_traceidratio"] = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = Field(default=1.0, ge=0.0, le=1.0)
    otel_metric_export_interval_ms: int = Field(default=15000, ge=1000, le=300000)
    capture_genai_content: bool = False
    git_commit_sha: str = ""
    build_version: str = ""

    # Google Gemini reasoning layer. `mock` is reserved for CI/development;
    # production agent execution uses the official Google Gen AI SDK.
    llm_mode: Literal["mock", "gemini"] = "mock"
    google_api_key: str = ""
    gemini_model: Literal["gemini-3.1-flash-lite"] = "gemini-3.1-flash-lite"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    gemini_max_retries: int = Field(default=2, ge=0, le=10)
    # Đơn giá token, USD trên một triệu token. Mặc định 0 = chưa khai giá, và
    # bảng điều khiển chi phí sẽ hiện 0 thay vì một con số bịa.
    gemini_input_usd_per_mtok: float = Field(default=0.0, ge=0)
    gemini_output_usd_per_mtok: float = Field(default=0.0, ge=0)
    # Cổng phơi chỉ số của worker. Worker không phục vụ HTTP nghiệp vụ nào, nên
    # cổng này chỉ dành cho Prometheus và không publish ra ngoài máy chủ.
    worker_metrics_port: int = Field(default=9108, ge=1, le=65535)

    # Explainable investigation workflow. These are hard safety budgets, not
    # suggestions passed to a model.
    #: Số vòng "viết bản giải thích → phản biện chấm → viết lại" cho một phiên.
    #:
    #: Nâng 3 → 5 vì đo được trên prod: cả 6 phiên trượt đều cạn VÒNG LẶP trong
    #: khi vẫn còn ngân sách công cụ (3/3 vòng nhưng mới 6–9/12 lượt gọi). Chúng
    #: bị cắt ngang lúc còn dư chỗ để tự sửa, chứ không phải bí thật.
    aml_agent_max_iterations: int = Field(default=5, ge=1, le=10)
    #: Trần lượt gọi công cụ cho một phiên điều tra.
    #:
    #: Nâng 8 → 12 khi thêm bước bổ sung bằng chứng bắt buộc. Quy trình tự gọi
    #: GetAccountBehavior và GetTransactions cho mọi cảnh báo — không có chúng
    #: thì bản diễn giải không mô tả được hành vi, chỉ nhắc lại điểm số. Hai lượt
    #: ấy ăn vào ngân sách, nên giữ trần 8 là bóp phần tác tử tự khám phá xuống
    #: còn 6 và phiên chạm trần trước khi kịp thu đủ chứng cứ.
    #:
    #: Vẫn TÍNH hai lượt bổ sung vào ngân sách chứ không miễn trừ: chúng là lượt
    #: gọi thật, có ghi vào `investigation_tool_call`. Miễn trừ sẽ khiến
    #: `tool_call_count` không khớp số bản ghi — một sai lệch tệ hơn.
    #:
    #: Nâng tiếp 12 → 16 cùng lúc với việc nới vòng lặp lên 5: thêm hai vòng mà
    #: giữ nguyên trần công cụ thì hai vòng ấy không có gì mới để đọc, chỉ viết
    #: lại trên đúng bằng chứng cũ.
    aml_agent_max_tool_calls: int = Field(default=16, ge=1, le=50)
    #: Chuyên viên tự đóng được vụ có điểm rủi ro DƯỚI ngưỡng này; từ ngưỡng
    #: trở lên phải qua Quản lý duyệt.
    #:
    #: Chọn 80 vì đó là lằn ranh "nghiêm trọng" hệ thống đã dùng ở hai chỗ khác
    #: (priority trong repository.create, và badge critical ở nav-counts) — thêm
    #: một con số thứ ba sẽ là thêm một định nghĩa "rủi ro cao" nữa.
    #:
    #: Đo trên production 27/08/2026: ngưỡng 80 giải phóng 2.794/14.267 vụ
    #: (19,6%). Không cao hơn được vì điểm MEGA-PNA bão hoà ở 100 (p25 = 99,98),
    #: nên ngưỡng theo điểm gần như không phân loại được nhánh IBM. Nới lên 99
    #: cũng chỉ tới 43,6%. Muốn thoát thật thì phải sửa chỗ điểm bão hoà, không
    #: phải chỗ ngưỡng này.
    case_self_close_max_risk: int = Field(default=80, ge=0, le=100)
    #: Phần đầu bản SAR xuất ra (tổ chức báo cáo và nơi nhận). Để ở cấu hình vì
    #: đây là thông tin của đơn vị triển khai, không phải dữ liệu của từng vụ.
    sar_institution_name: str = "NGÂN HÀNG VELRIX"
    sar_institution_unit: str = "Khối Tuân thủ — Bộ phận Phòng, chống rửa tiền"
    sar_recipient: str = "Cục Phòng, chống rửa tiền — Ngân hàng Nhà nước Việt Nam"

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

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    @model_validator(mode="after")
    def validate_gemini_runtime(self) -> Self:
        if self.app_env == "production" and self.llm_mode != "gemini":
            raise ValueError("LLM_MODE=gemini is required in production")
        if self.app_env == "production" and self.capture_genai_content:
            raise ValueError("CAPTURE_GENAI_CONTENT is forbidden in production")
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
