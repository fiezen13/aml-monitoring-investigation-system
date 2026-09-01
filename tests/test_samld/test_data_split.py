"""Test loader canonical + dẫn xuất đặc trưng + chia thời gian không leakage."""

from __future__ import annotations

from pathlib import Path

from src.samld.config import SamldConfig
from src.samld.data import load_samld
from src.samld.schema import EDGE_FEATURE_SOURCE_COLUMNS, assert_no_label_leakage
from src.samld.split import assert_temporal_order, temporal_split


def _config(csv: Path) -> SamldConfig:
    return SamldConfig(raw_csv=csv)


def test_load_canonical_and_derived(raw_samld_csv: Path) -> None:
    df = load_samld(_config(raw_samld_csv))
    # cột canonical + dẫn xuất có mặt
    for col in ("sender_account", "receiver_account", "amount", "sender_country", "label", "typology"):
        assert col in df.columns
    for col in EDGE_FEATURE_SOURCE_COLUMNS:
        assert col in df.columns
    # cross_border / currency_mismatch là nhị phân 0/1
    assert set(df["cross_border"].unique()) <= {0.0, 1.0}
    assert set(df["currency_mismatch"].unique()) <= {0.0, 1.0}
    # transaction_id duy nhất
    assert df["transaction_id"].is_unique


def test_derived_features_not_leaking_labels(raw_samld_csv: Path) -> None:
    # Gọi để chắc loader chạy được trên dữ liệu mẫu (ném lỗi nếu hỏng).
    load_samld(_config(raw_samld_csv))
    # đặc trưng cạnh dùng để train KHÔNG được chứa nhãn
    assert_no_label_leakage(list(EDGE_FEATURE_SOURCE_COLUMNS))


def test_temporal_split_strict_order(raw_samld_csv: Path) -> None:
    df = load_samld(_config(raw_samld_csv))
    split = temporal_split(df, _config(raw_samld_csv))
    assert len(split.train) > 0 and len(split.val) > 0 and len(split.test) > 0
    assert len(split.train) + len(split.val) + len(split.test) == len(df)
    # bất biến thời gian: train < val < test (ném lỗi nếu vi phạm)
    assert_temporal_order(split)
    assert split.train["timestamp"].max() < split.val["timestamp"].min()
    assert split.val["timestamp"].max() < split.test["timestamp"].min()
