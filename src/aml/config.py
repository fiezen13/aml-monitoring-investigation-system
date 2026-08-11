"""Cấu hình luồng nạp AML, đọc từ biến môi trường.

Tách khỏi `src.config.Settings` có chủ ý: đó là cấu hình của API và worker
(PostgreSQL, Redis, LLM), còn đây là cấu hình của một tiến trình phát lại dữ
liệu hoàn toàn khác, chạy độc lập và thường chạy trong container riêng.

Ràng buộc tài liệu vẫn giữ nguyên như phần còn lại của repo: mọi trường ở
đây phải có mặt trong `.env.example` và `.env.example`, và
`tests/test_config_documented.py` kiểm tra điều đó ở mỗi lần chạy CI.
"""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ReplayMode = Literal["max-throughput", "event-time"]


class AmlSettings(BaseSettings):
    """Biến môi trường điều khiển producer phát lại CSV.

    Không trường nào bắt buộc: mặc định chạy được với bộ `HI-Small` đặt ở
    `data/raw/ibm-aml/` và Kafka ở `localhost:29092`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Nguồn dữ liệu ------------------------------------------------
    # Đường dẫn cấu hình được: đổi sang LI-Small / HI-Medium / HI-Large chỉ
    # cần đổi biến này. Không nơi nào trong mã ghi cứng tên file.
    aml_csv_path: str = "data/raw/ibm-aml/HI-Small_Trans.csv"
    # Để trống thì suy ra từ tên file: `HI-Small_Trans.csv` → `HI-Small`.
    aml_source_dataset: str = ""
    # Múi giờ của cột Timestamp trong bộ dữ liệu. Bộ dữ liệu IBM không ghi
    # múi giờ, nên đây là một giả định phải khai báo rõ chứ không đoán.
    dataset_timezone: str = "UTC"

    # ---- Kafka --------------------------------------------------------
    kafka_bootstrap_servers: str = "localhost:29092"
    aml_raw_topic: str = "aml.transactions.raw.v1"
    aml_dlq_topic: str = "aml.transactions.dlq.v1"
    aml_topic_partitions: int = Field(default=3, ge=1, le=1000)
    aml_topic_replication_factor: int = Field(default=1, ge=1, le=10)
    # lz4 nhanh và rẻ CPU hơn gzip ở cùng mức nén cho dữ liệu giao dịch.
    kafka_compression_type: Literal["none", "gzip", "snappy", "lz4", "zstd"] = "lz4"
    kafka_linger_ms: int = Field(default=20, ge=0, le=60_000)
    kafka_batch_size: int = Field(default=262_144, ge=1024)
    # Trần số message đang chờ trong hàng đợi nội bộ của librdkafka. Đây
    # chính là cơ chế backpressure: chạm trần thì producer chặn lại chờ,
    # không phình bộ nhớ.
    kafka_queue_buffering_max_messages: int = Field(default=100_000, ge=1000)
    kafka_message_timeout_ms: int = Field(default=120_000, ge=1000)

    # ---- Chế độ phát lại ----------------------------------------------
    replay_mode: ReplayMode = "max-throughput"
    # 1 = tốc độ thật, 10 = nhanh gấp mười, 0 = không chờ.
    replay_speed_multiplier: float = Field(default=1.0, ge=0.0)
    # Trần thời gian chờ giữa hai sự kiện, để một khoảng trống dài trong dữ
    # liệu không làm tiến trình treo hàng giờ.
    replay_max_sleep_seconds: float = Field(default=5.0, ge=0.0)

    # ---- Giới hạn dữ liệu khi phát triển -------------------------------
    max_records: int = Field(default=0, ge=0)  # 0 = không giới hạn
    start_line: int = Field(default=0, ge=0)  # số dòng dữ liệu, 0 = từ đầu
    end_line: int = Field(default=0, ge=0)  # 0 = tới hết file
    from_timestamp: str = ""  # ISO-8601, lọc theo event time nguồn
    to_timestamp: str = ""

    # ---- Điểm dừng để chạy tiếp ---------------------------------------
    aml_checkpoint_enabled: bool = True
    aml_checkpoint_path: str = "data/aml/checkpoints/producer.json"
    aml_checkpoint_interval_seconds: float = Field(default=5.0, gt=0)
    # Bỏ qua checkpoint và chạy lại từ đầu.
    aml_resume: bool = True

    # ---- Dòng lỗi -----------------------------------------------------
    aml_dlq_enabled: bool = True
    aml_error_log_path: str = "data/aml/rejected/producer-errors.jsonl"

    # ---- Nhật ký tiến độ ----------------------------------------------
    aml_progress_every_seconds: float = Field(default=10.0, gt=0)
    aml_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("dataset_timezone")
    @classmethod
    def _timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:  # pragma: no cover - phụ thuộc hệ thống
            raise ValueError(f"DATASET_TIMEZONE={value!r} không phải múi giờ IANA hợp lệ") from exc
        return value

    # ---- Giá trị dẫn xuất ---------------------------------------------

    @property
    def csv_path(self) -> Path:
        return Path(self.aml_csv_path)

    @property
    def source_dataset(self) -> str:
        """Tên bộ dữ liệu, ví dụ `HI-Small`.

        Suy ra từ tên file khi không được đặt tường minh, theo quy ước đặt
        tên của bộ IBM: `<Bộ>_Trans.csv`.
        """
        if self.aml_source_dataset:
            return self.aml_source_dataset
        return derive_source_dataset(self.csv_path.name)

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.dataset_timezone)

    @property
    def from_datetime(self) -> datetime | None:
        return _parse_bound(self.from_timestamp, self.tzinfo)

    @property
    def to_datetime(self) -> datetime | None:
        return _parse_bound(self.to_timestamp, self.tzinfo)


def derive_source_dataset(file_name: str) -> str:
    """`HI-Small_Trans.csv` → `HI-Small`; tên lạ thì lấy phần trước dấu chấm."""
    stem = Path(file_name).stem
    for suffix in ("_Trans", "_trans"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _parse_bound(raw: str, tz: ZoneInfo) -> datetime | None:
    """Đọc mốc lọc thời gian. Không có múi giờ thì hiểu theo múi giờ bộ dữ liệu."""
    if not raw.strip():
        return None
    text = raw.strip().replace("/", "-")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


@lru_cache
def get_aml_settings() -> AmlSettings:
    return AmlSettings()
