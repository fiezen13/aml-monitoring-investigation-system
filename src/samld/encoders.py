"""Mã hoá đặc trưng cạnh SAML-D — categorical một-nóng + chuẩn hoá số, FIT TRÊN TRAIN.

Vì sao one-hot cho quốc gia/tiền tệ/kiểu thanh toán: KHÔNG được ordinal-encode để
model hiểu ``UK < UAE < Turkey`` (§8). One-hot là biểu diễn categorical trung
tính, và giữ country ở mức NGỮ CẢNH — không có điểm rủi ro FATF nào.

Vì sao fit trên TRAIN: từ vựng category và thống kê chuẩn hoá chỉ được học từ
train, áp cho val/test. Category lạ ở test → vector 0 (``handle_unknown='ignore'``),
không lỗi. Điều này chặt hơn cách chuẩn hoá theo lát của mega_pna và tránh rò rỉ
phân phối từ tương lai.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder

from src.samld.schema import (
    BINARY_EDGE_FEATURES,
    CATEGORICAL_EDGE_FEATURES,
    NUMERIC_EDGE_FEATURES,
    assert_no_label_leakage,
)


@dataclass
class EdgeEncoder:
    """Bộ mã hoá đặc trưng cạnh đã fit — dùng lại cho val/test/inference."""

    onehot: OneHotEncoder
    numeric_mean: np.ndarray
    numeric_std: np.ndarray
    feature_names: list[str]

    @property
    def num_features(self) -> int:
        return len(self.feature_names)

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """DataFrame canonical → ma trận đặc trưng cạnh float32 (đã chuẩn hoá)."""
        numeric = df[list(NUMERIC_EDGE_FEATURES)].to_numpy(dtype=np.float64)
        numeric = (numeric - self.numeric_mean) / self.numeric_std
        binary = df[list(BINARY_EDGE_FEATURES)].to_numpy(dtype=np.float64)
        cat = self.onehot.transform(df[list(CATEGORICAL_EDGE_FEATURES)].astype(str))
        matrix = np.concatenate([numeric, binary, cat], axis=1).astype(np.float32)
        return matrix

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        np.savez(path / "numeric_scaler.npz", mean=self.numeric_mean, std=self.numeric_std)
        (path / "feature_names.json").write_text(
            json.dumps(self.feature_names, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # OneHotEncoder categories_ đủ để tái dựng tất định.
        cats = [list(map(str, c)) for c in self.onehot.categories_]
        (path / "onehot_categories.json").write_text(
            json.dumps({"columns": list(CATEGORICAL_EDGE_FEATURES), "categories": cats}, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> EdgeEncoder:
        scaler = np.load(path / "numeric_scaler.npz")
        names = json.loads((path / "feature_names.json").read_text(encoding="utf-8"))
        spec = json.loads((path / "onehot_categories.json").read_text(encoding="utf-8"))
        onehot = OneHotEncoder(
            categories=[np.array(c, dtype=object) for c in spec["categories"]],
            handle_unknown="ignore",
            sparse_output=False,
            dtype=np.float64,
        )
        # fit rỗng để khởi tạo với categories cố định.
        onehot.fit(pd.DataFrame({col: cats[:1] or [""] for col, cats in zip(spec["columns"], spec["categories"])}))
        return cls(onehot=onehot, numeric_mean=scaler["mean"], numeric_std=scaler["std"], feature_names=names)


def fit_edge_encoder(train_df: pd.DataFrame) -> EdgeEncoder:
    """Fit bộ mã hoá TRÊN TRAIN. Không bao giờ nhìn val/test.

    Tên đặc trưng đầu ra được kiểm chống rò rỉ nhãn trước khi trả về.
    """
    onehot = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float64)
    onehot.fit(train_df[list(CATEGORICAL_EDGE_FEATURES)].astype(str))

    numeric = train_df[list(NUMERIC_EDGE_FEATURES)].to_numpy(dtype=np.float64)
    mean = numeric.mean(axis=0)
    std = numeric.std(axis=0)
    std[std == 0] = 1.0

    cat_names = [f"{col}={val}" for col, cats in zip(CATEGORICAL_EDGE_FEATURES, onehot.categories_) for val in cats]
    feature_names = list(NUMERIC_EDGE_FEATURES) + list(BINARY_EDGE_FEATURES) + cat_names
    assert_no_label_leakage(feature_names)
    return EdgeEncoder(onehot=onehot, numeric_mean=mean, numeric_std=std, feature_names=feature_names)
