"""Cấu hình nhánh SAML-D — đường dẫn, chia tách, ngưỡng, seed.

Bám quy ước của ``src/bitcoin_aml/config.py``: dataclass frozen, đường dẫn lấy từ
biến môi trường ``SAMLD_*`` với mặc định trỏ vào repo. Toàn bộ siêu tham số nằm
trong YAML (``config/default.yaml``, ``config/benchmark.yaml``); dataclass này
chỉ giữ các hằng đường dẫn/split cần cho mọi lần chạy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


@dataclass(frozen=True)
class SamldConfig:
    """Đường dẫn và tham số chia tách cố định cho nhánh SAML-D."""

    #: CSV thô SAML-D (đặt ở gốc repo theo hiện trạng).
    raw_csv: Path = field(default_factory=lambda: _env_path("SAMLD_RAW_CSV", ROOT / "SAML-D.csv"))
    #: Thư mục artifact xử lý sẵn (parquet, encoders, profile).
    processed_dir: Path = field(default_factory=lambda: _env_path("SAMLD_PROCESSED_DIR", ROOT / "data/processed/samld"))
    #: Thư mục checkpoint model + threshold + metrics.
    model_dir: Path = field(default_factory=lambda: _env_path("SAMLD_MODEL_DIR", ROOT / "data/models/samld"))
    #: Thư mục artifact benchmark (bảng, hình, report).
    artifact_dir: Path = field(default_factory=lambda: _env_path("SAMLD_ARTIFACT_DIR", ROOT / "artifacts/samld"))

    # --- Chia tách theo thời gian (chronological). Không random làm mặc định. ---
    train_fraction: float = field(default_factory=lambda: _env_float("SAMLD_TRAIN_FRACTION", 0.70))
    val_fraction: float = field(default_factory=lambda: _env_float("SAMLD_VAL_FRACTION", 0.15))
    # test = phần còn lại (0.15). Ràng buộc: train.time < val.time < test.time.

    #: Seed mặc định; benchmark chạy nhiều seed qua config.
    random_seed: int = 42

    def __post_init__(self) -> None:
        total = self.train_fraction + self.val_fraction
        if not 0 < total < 1:
            raise ValueError(f"train+val fraction phải trong (0,1) để còn phần test; nhận {total:.3f}.")


def get_samld_config() -> SamldConfig:
    return SamldConfig()
