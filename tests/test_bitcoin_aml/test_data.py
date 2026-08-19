"""Kiểm tra loader và chia dữ liệu theo thời gian của nhánh Bitcoin AML."""

from __future__ import annotations

import dataclasses

import pytest

from src.bitcoin_aml.data import ILLICIT, LICIT, DatasetError, load_elliptic, temporal_split


def test_missing_dataset_raises_clear_error(elliptic_shaped):
    config = dataclasses.replace(elliptic_shaped, data_dir=elliptic_shaped.data_dir / "khong-ton-tai")
    with pytest.raises(DatasetError, match="Không thấy"):
        load_elliptic(config)


def test_unknown_labels_are_dropped_from_supervised_set(elliptic_shaped):
    loaded = load_elliptic(elliptic_shaped)
    assert loaded.class_distribution["unknown"] > 0  # có unknown trong dữ liệu
    split = temporal_split(loaded, elliptic_shaped)
    # Tập giám sát chỉ còn illicit/licit — unknown không lọt vào.
    assert set(split.y_train.unique()) <= {ILLICIT, LICIT}
    assert set(split.y_test.unique()) <= {ILLICIT, LICIT}


def test_temporal_split_has_no_future_leakage(elliptic_shaped):
    """Test toàn bước thời gian > mốc train; train toàn bước ≤ mốc."""
    loaded = load_elliptic(elliptic_shaped)
    split = temporal_split(loaded, elliptic_shaped)
    time_col = loaded.time_column
    # Không thể so trực tiếp x_test (đã bỏ cột thời gian), nên so qua timesteps ghi lại.
    assert split.test_timesteps[0] > elliptic_shaped.train_last_timestep
    assert split.train_timesteps[1] == elliptic_shaped.train_last_timestep
    assert time_col == "Time step"


def test_unexpected_class_value_is_rejected(elliptic_shaped, tmp_path):
    import pandas as pd

    bad = pd.read_csv(elliptic_shaped.classes_path)
    bad.loc[0, "class"] = "7"  # giá trị lớp không hợp lệ
    bad.to_csv(elliptic_shaped.classes_path, index=False)
    with pytest.raises(DatasetError, match="giá trị lớp lạ"):
        load_elliptic(elliptic_shaped)


def test_feature_columns_exclude_id_and_time(elliptic_shaped):
    loaded = load_elliptic(elliptic_shaped)
    assert loaded.id_column not in loaded.feature_names
    assert loaded.time_column not in loaded.feature_names
    assert "label" not in loaded.feature_names  # nhãn không phải đặc trưng
