"""Cấu hình nhánh Bitcoin AML — đường dẫn, siêu tham số, ngưỡng vận hành.

Theo đúng quy ước của ``src/mega_pna/config.py``: siêu tham số nằm trong một
dataclass đóng băng, KHÔNG nhồi vào ``Settings`` toàn cục (mỗi trường ở đó phải
được ghi vào ``.env.example`` và có test kiểm tra). Những gì cần chỉnh theo môi
trường thì đọc từ biến môi trường với giá trị mặc định hợp lý.

Không hard-code đường dẫn tuyệt đối của máy developer: mọi đường dẫn suy ra từ
gốc repo hoặc từ biến môi trường ``BITCOIN_AML_*``.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Gốc repo, suy ra từ vị trí file — không phụ thuộc thư mục làm việc.
ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class RiskThresholds:
    """Ngưỡng vận hành ánh xạ P(illicit) sang mức rủi ro.

    Đây là ngưỡng VẬN HÀNH, không phải nhãn ground-truth: nó chỉ quyết định khi
    nào đẩy một giao dịch lên hàng rà soát, và có thể chỉnh mà không huấn luyện
    lại. Đọc được từ biến môi trường để mỗi môi trường tự đặt khẩu vị rủi ro.
    """

    medium: float = 0.50
    high: float = 0.75
    critical: float = 0.90

    @classmethod
    def from_env(cls) -> RiskThresholds:
        return cls(
            medium=_env_float("BITCOIN_AML_THRESHOLD_MEDIUM", 0.50),
            high=_env_float("BITCOIN_AML_THRESHOLD_HIGH", 0.75),
            critical=_env_float("BITCOIN_AML_THRESHOLD_CRITICAL", 0.90),
        )

    def level(self, risk_score: float) -> str:
        """Xếp một xác suất illicit vào mức rủi ro vận hành."""
        if risk_score >= self.critical:
            return "CRITICAL"
        if risk_score >= self.high:
            return "HIGH"
        if risk_score >= self.medium:
            return "MEDIUM"
        return "LOW"


@dataclass(frozen=True)
class BitcoinAmlConfig:
    """Toàn bộ cấu hình của nhánh Bitcoin AML.

    Chia rõ ba nhóm: đường dẫn dữ liệu/artifact, siêu tham số Random Forest, và
    giao thức chia dữ liệu theo thời gian. Giá trị mặc định bám theo giao thức
    Elliptic đã công bố (Weber et al. 2019, Elliptic++ 2023) để tái lập được,
    không phải để dò SOTA.
    """

    # --- Đường dẫn: dữ liệu thô Elliptic++ và artifact mô hình ---------------
    data_dir: Path = field(default_factory=lambda: _env_path("BITCOIN_AML_DATA_DIR", ROOT / "data/raw/elliptic++"))
    artifact_dir: Path = field(
        default_factory=lambda: _env_path("BITCOIN_AML_ARTIFACT_DIR", ROOT / "data/models/bitcoin_aml")
    )
    #: Tên file trong ``data_dir`` — đúng tên của repo Elliptic++ chính thức.
    features_file: str = "txs_features.csv"
    classes_file: str = "txs_classes.csv"
    edgelist_file: str = "txs_edgelist.csv"

    # --- Cột định danh trong file feature ------------------------------------
    #: Cột mã giao dịch và cột bước thời gian. Loader dò linh hoạt nhưng ưu tiên
    #: các tên này, khớp với header của Elliptic++.
    id_column_candidates: tuple[str, ...] = ("txId", "txID", "id", "transaction_id")
    time_column_candidates: tuple[str, ...] = ("Time step", "time_step", "timestep", "Timestep", "time")

    # --- Ánh xạ nhãn: giá trị THẬT trong txs_classes.csv của Elliptic++ ------
    #: ``1`` = illicit, ``2`` = licit, ``unknown``/``3`` = chưa gán nhãn. Loader
    #: kiểm chứng lại từ chính file và báo lỗi nếu gặp giá trị lạ, thay vì đoán.
    label_illicit: str = "1"
    label_licit: str = "2"
    label_unknown_values: tuple[str, ...] = ("unknown", "3")

    # --- Chia dữ liệu THEO THỜI GIAN (không random, tránh rò rỉ tương lai) ---
    #: Giao thức Elliptic chuẩn: bước ≤ 34 để huấn luyện, ≥ 35 để kiểm thử. Một
    #: phần cuối của train tách ra làm validation để chốt refinement/ngưỡng.
    train_last_timestep: int = 34
    validation_last_timestep: int = 34  # validation nằm TRONG khối train, cắt theo tỉ lệ
    validation_fraction: float = 0.15  # 15% timestep cuối của khối train làm validation

    # --- Random Forest (bám theo Weber et al. / Elliptic++) ------------------
    n_estimators: int = 100
    max_depth: int | None = None
    max_features: str | int | float = "sqrt"
    min_samples_leaf: int = 1
    #: 'balanced_subsample' xử lý mất cân bằng lớp (illicit ~2%) mà không cần
    #: SMOTE — không tạo mẫu tổng hợp trước khi chia, nên không rò rỉ.
    class_weight: str = "balanced_subsample"
    random_seed: int = 42
    n_jobs: int = -1

    # --- Feature refinement ---------------------------------------------------
    #: Giữ số đặc trưng đủ để phủ tỉ lệ này của tổng độ quan trọng (impurity),
    #: tính TRÊN TẬP TRAIN. Tinh gọn đặc trưng theo độ quan trọng là cách tái lập
    #: trung thực bước "feature refinement" của paper mà không bịa ngữ nghĩa cho
    #: các đặc trưng vốn ẩn danh.
    refinement_importance_coverage: float = 0.95
    #: Trần cứng số đặc trưng giữ lại, để bản tinh gọn thực sự nhỏ hơn bản đầy đủ.
    refinement_max_features: int = 60

    thresholds: RiskThresholds = field(default_factory=RiskThresholds.from_env)

    # --- Artifact filenames ---------------------------------------------------
    model_filename: str = "bitcoin_rf.joblib"
    feature_metadata_filename: str = "feature_metadata.json"
    metrics_filename: str = "training_metrics.json"
    model_metadata_filename: str = "model_metadata.json"

    @property
    def features_path(self) -> Path:
        return self.data_dir / self.features_file

    @property
    def classes_path(self) -> Path:
        return self.data_dir / self.classes_file

    @property
    def edgelist_path(self) -> Path:
        return self.data_dir / self.edgelist_file

    @property
    def model_path(self) -> Path:
        return self.artifact_dir / self.model_filename

    @property
    def feature_metadata_path(self) -> Path:
        return self.artifact_dir / self.feature_metadata_filename

    @property
    def metrics_path(self) -> Path:
        return self.artifact_dir / self.metrics_filename

    @property
    def model_metadata_path(self) -> Path:
        return self.artifact_dir / self.model_metadata_filename

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        # Path và tuple không tuần tự hoá thẳng sang JSON được.
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        data["thresholds"] = asdict(self.thresholds)
        return data


def get_bitcoin_config() -> BitcoinAmlConfig:
    """Cấu hình mặc định, đọc override từ môi trường."""
    return BitcoinAmlConfig()
