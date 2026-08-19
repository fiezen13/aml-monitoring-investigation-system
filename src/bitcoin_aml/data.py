"""Nạp và tiền xử lý bộ dữ liệu giao dịch Elliptic++.

Ba file thô của Elliptic++ (đúng tên repo chính thức):

* ``txs_features.csv``  — mã giao dịch, bước thời gian, và các đặc trưng ẩn danh.
* ``txs_classes.csv``   — mã giao dịch → lớp (1 illicit / 2 licit / unknown).
* ``txs_edgelist.csv``  — cạnh giao dịch → giao dịch (dùng cho ngữ cảnh đồ thị).

Nguyên tắc bất di bất dịch
--------------------------
* **Chia theo thời gian, không random.** Bitcoin là dữ liệu thời gian; random
  split để thông tin tương lai rò về quá khứ. Bước ≤ ``train_last_timestep`` để
  huấn luyện, phần sau để kiểm thử. (Weber et al. 2019; Elliptic++ 2023.)
* **UNKNOWN không phải LICIT.** Giao dịch chưa gán nhãn bị LOẠI khỏi tập giám
  sát, đúng như giao thức paper — không mặc định coi là hợp pháp.
* **Không rò rỉ.** Mọi thống kê (độ quan trọng đặc trưng, ngưỡng) tính trên
  train; test chỉ được chạm tới ở bước đánh giá cuối.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.bitcoin_aml.config import BitcoinAmlConfig

logger = logging.getLogger("fin07.bitcoin_aml.data")

#: Nhãn số nội bộ dùng cho học giám sát: illicit là lớp DƯƠNG.
ILLICIT = 1
LICIT = 0


class DatasetError(Exception):
    """Dữ liệu Elliptic++ thiếu hoặc sai cấu trúc so với kỳ vọng."""


@dataclass(frozen=True)
class LoadedElliptic:
    """Bộ dữ liệu đã nạp và gán nhãn, TRƯỚC khi chia hay tinh gọn đặc trưng."""

    frame: pd.DataFrame  # gồm id_col, time_col, feature_names..., 'label' (1/0/NaN)
    feature_names: list[str]
    id_column: str
    time_column: str
    class_distribution: dict[str, int]


@dataclass(frozen=True)
class SplitData:
    """Ba tập chia theo thời gian, chỉ chứa giao dịch đã gán nhãn (illicit/licit)."""

    x_train: pd.DataFrame
    y_train: pd.Series
    x_val: pd.DataFrame
    y_val: pd.Series
    x_test: pd.DataFrame
    y_test: pd.Series
    feature_names: list[str]
    time_column: str
    train_timesteps: tuple[int, int]
    test_timesteps: tuple[int, int]


def _pick_column(columns: list[str], candidates: tuple[str, ...], role: str) -> str:
    """Chọn cột định danh/thời gian theo danh sách ứng viên, báo lỗi rõ nếu thiếu."""
    for candidate in candidates:
        if candidate in columns:
            return candidate
    # Elliptic++ đôi khi để file không header với cột 0 là id, cột 1 là thời gian.
    raise DatasetError(
        f"Không tìm thấy cột {role} trong {columns[:5]}… — thử một trong {candidates}. "
        "Nếu file không có header, hãy dùng bản có header của repo Elliptic++."
    )


def load_elliptic(config: BitcoinAmlConfig) -> LoadedElliptic:
    """Nạp ba file, nối nhãn vào đặc trưng, kiểm chứng cấu trúc.

    KHÔNG chạm cột nhãn vào đặc trưng: nhãn chỉ dùng để giám sát, không phải một
    đặc trưng — trộn vào là rò rỉ đáp án.
    """
    features_path = config.features_path
    classes_path = config.classes_path
    if not features_path.exists():
        raise DatasetError(
            f"Không thấy {features_path}. Đặt bộ Elliptic++ vào {config.data_dir} "
            f"với các file {config.features_file}, {config.classes_file}, {config.edgelist_file}."
        )
    if not classes_path.exists():
        raise DatasetError(f"Không thấy {classes_path}.")

    features = pd.read_csv(features_path)
    classes = pd.read_csv(classes_path)

    id_col = _pick_column(list(features.columns), config.id_column_candidates, "mã giao dịch")
    time_col = _pick_column(list(features.columns), config.time_column_candidates, "bước thời gian")
    class_id_col = _pick_column(list(classes.columns), config.id_column_candidates, "mã giao dịch (classes)")
    class_col = next((c for c in classes.columns if c != class_id_col), None)
    if class_col is None:
        raise DatasetError("txs_classes.csv chỉ có một cột — thiếu cột lớp.")

    feature_names = [c for c in features.columns if c not in (id_col, time_col)]
    if not feature_names:
        raise DatasetError("Không có cột đặc trưng nào sau khi bỏ mã và bước thời gian.")

    # Nối nhãn theo mã giao dịch. Ép mã về chuỗi để không lệch kiểu int/str.
    features = features.copy()
    features[id_col] = features[id_col].astype(str)
    classes = classes.copy()
    classes[class_id_col] = classes[class_id_col].astype(str)
    class_map = dict(zip(classes[class_id_col], classes[class_col].astype(str), strict=False))

    raw_class = features[id_col].map(class_map)
    observed = set(raw_class.dropna().unique())
    known = {config.label_illicit, config.label_licit, *config.label_unknown_values}
    unexpected = observed - known
    if unexpected:
        raise DatasetError(
            f"txs_classes.csv có giá trị lớp lạ {sorted(unexpected)}; kỳ vọng "
            f"{sorted(known)}. Kiểm tra lại ánh xạ nhãn trong config trước khi huấn luyện."
        )

    def to_label(value: object) -> float:
        text = str(value)
        if text == config.label_illicit:
            return float(ILLICIT)
        if text == config.label_licit:
            return float(LICIT)
        return float("nan")  # unknown → không gán nhãn

    features["label"] = raw_class.map(to_label)

    distribution = {
        "illicit": int((features["label"] == ILLICIT).sum()),
        "licit": int((features["label"] == LICIT).sum()),
        "unknown": int(features["label"].isna().sum()),
        "total": int(len(features)),
    }
    logger.info("Elliptic++ nạp xong: %s", distribution)

    return LoadedElliptic(
        frame=features,
        feature_names=feature_names,
        id_column=id_col,
        time_column=time_col,
        class_distribution=distribution,
    )


def _sanitize(frame: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Thay vô hạn/NaN trong đặc trưng bằng 0, chỉ trên cột đặc trưng.

    Elliptic++ hiếm khi có NaN, nhưng một giá trị vô hạn lọt qua sẽ làm hỏng cả
    lần huấn luyện. Xử lý ở một chỗ để suy luận và huấn luyện giống hệt nhau.
    """
    out = frame.copy()
    out[feature_names] = out[feature_names].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float32)
    return out


def temporal_split(loaded: LoadedElliptic, config: BitcoinAmlConfig) -> SplitData:
    """Chia theo bước thời gian; chỉ giữ giao dịch đã gán nhãn (illicit/licit).

    Validation cắt từ phần CUỐI của khối train (các bước thời gian muộn nhất
    trong train), để bước tinh gọn đặc trưng và chốt ngưỡng không bao giờ nhìn
    thấy test.
    """
    frame = _sanitize(loaded.frame, loaded.feature_names)
    time_col = loaded.time_column
    labelled = frame[frame["label"].notna()].copy()
    labelled["label"] = labelled["label"].astype(int)

    train_mask = labelled[time_col] <= config.train_last_timestep
    test_mask = labelled[time_col] > config.train_last_timestep
    train_all = labelled[train_mask]
    test = labelled[test_mask]
    if train_all.empty or test.empty:
        raise DatasetError(
            f"Chia theo thời gian rỗng: train={len(train_all)}, test={len(test)}. "
            f"Kiểm tra train_last_timestep={config.train_last_timestep} so với dải bước thời gian thực tế."
        )

    # Validation = các bước thời gian muộn nhất trong khối train.
    train_steps = sorted(train_all[time_col].unique())
    n_val_steps = max(1, round(len(train_steps) * config.validation_fraction))
    val_steps = set(train_steps[-n_val_steps:])
    val_mask = train_all[time_col].isin(val_steps)
    val = train_all[val_mask]
    train = train_all[~val_mask]

    def xy(part: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        return part[loaded.feature_names], part["label"]

    x_train, y_train = xy(train)
    x_val, y_val = xy(val)
    x_test, y_test = xy(test)
    logger.info(
        "Chia thời gian: train=%d (bước %d–%d), val=%d, test=%d (bước %d–%d)",
        len(x_train),
        train_steps[0],
        max(s for s in train_steps if s not in val_steps),
        len(x_val),
        len(x_test),
        min(test[time_col]),
        max(test[time_col]),
    )
    return SplitData(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        x_test=x_test,
        y_test=y_test,
        feature_names=loaded.feature_names,
        time_column=time_col,
        train_timesteps=(int(train_steps[0]), int(config.train_last_timestep)),
        test_timesteps=(int(test[time_col].min()), int(test[time_col].max())),
    )
