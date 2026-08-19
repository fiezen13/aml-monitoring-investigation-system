"""Fixture dựng một bộ dữ liệu HÌNH DẠNG Elliptic++ để chạy hết đường ống.

Đây KHÔNG phải dữ liệu Elliptic++ thật — nó chỉ tái tạo đúng cấu trúc file
(txs_features / txs_classes / txs_edgelist, cột bước thời gian, ba lớp
1/2/unknown) để kiểm tra loader, chia thời gian, tinh gọn đặc trưng, huấn luyện,
suy luận và API chạy đúng. Con số chất lượng mô hình chỉ có ý nghĩa trên dữ liệu
thật; ở đây ta chỉ khẳng định ĐƯỜNG ỐNG đúng, không khẳng định F1.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.bitcoin_aml.config import get_bitcoin_config


@pytest.fixture
def elliptic_shaped(tmp_path: Path):
    """Sinh dữ liệu hình Elliptic++ vào tmp và trả config trỏ vào đó.

    - 12 đặc trưng (đủ để có gì mà tinh gọn), 8 bước thời gian.
    - Lớp illicit tách được tuyến tính khỏi licit ở vài đặc trưng, để rừng học
      được và cho xác suất phân tách — kiểm tra được predict_proba nằm trong [0,1]
      và feature refinement bỏ bớt đặc trưng nhiễu.
    - Có cả unknown, để khẳng định chúng bị loại khỏi tập giám sát.
    """
    rng = np.random.default_rng(0)
    data_dir = tmp_path / "elliptic++"
    data_dir.mkdir()
    n = 900
    n_features = 12
    timesteps = rng.integers(1, 9, size=n)  # 1..8

    signal = rng.normal(size=n)
    x = rng.normal(size=(n, n_features)).astype(np.float32)
    # Ba đặc trưng đầu mang tín hiệu; phần còn lại là nhiễu (sẽ bị tinh gọn loại).
    x[:, 0] += signal * 2.0
    x[:, 1] += signal * 1.5
    x[:, 2] -= signal * 1.2

    # Nhãn: ~15% illicit (tín hiệu cao), phần lớn licit, một phần unknown.
    prob_illicit = 1 / (1 + np.exp(-signal))
    roll = rng.random(n)
    label = np.where(roll < 0.15, "1", "2")  # 1 illicit, 2 licit
    label = np.where((prob_illicit > 0.5) & (roll < 0.30), "1", label)
    # 25% unknown rải đều
    label = np.where(rng.random(n) < 0.25, "unknown", label)

    tx_ids = [f"tx{i}" for i in range(n)]
    feat_cols = {f"feature_{j}": x[:, j] for j in range(n_features)}
    features = pd.DataFrame({"txId": tx_ids, "Time step": timesteps, **feat_cols})
    classes = pd.DataFrame({"txId": tx_ids, "class": label})
    # Vài cạnh giao dịch→giao dịch cho tiện ích đồ thị.
    edges = pd.DataFrame({"txId1": tx_ids[:-1], "txId2": tx_ids[1:]})

    features.to_csv(data_dir / "txs_features.csv", index=False)
    classes.to_csv(data_dir / "txs_classes.csv", index=False)
    edges.to_csv(data_dir / "txs_edgelist.csv", index=False)

    return dataclasses.replace(
        get_bitcoin_config(),
        data_dir=data_dir,
        artifact_dir=tmp_path / "artifacts",
        train_last_timestep=5,  # bước ≤5 train, 6..8 test
        n_estimators=40,
        refinement_max_features=8,
    )
