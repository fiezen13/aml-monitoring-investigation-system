"""Chia SAML-D theo THỜI GIAN (chronological) — không rò rỉ tương lai.

Benchmark chính bắt buộc: ``max(train.time) < min(val.time) < min(test.time)``.
Random stratified split chỉ được phép như thí nghiệm phụ, không phải mặc định.

Vì mốc thời gian có thể trùng ở ranh giới, ta cắt theo phân vị rồi ĐẨY toàn bộ
dòng cùng mốc ở ranh giới về phía sớm hơn, để bất đẳng thức nghiêm ngặt luôn giữ.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from src.samld.config import SamldConfig, get_samld_config
from src.samld.schema import COLS

logger = logging.getLogger("fin07.samld.split")


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_end: pd.Timestamp
    val_end: pd.Timestamp


def _cut_at_boundary(ordered: pd.DataFrame, cut: int) -> int:
    """Đẩy điểm cắt để không tách các dòng cùng một mốc thời gian.

    Mọi dòng có cùng timestamp với dòng tại ``cut`` phải nằm cùng một bên; đưa
    chúng về phía TRƯỚC (train/val), để split sau không thấy mốc đã xuất hiện.
    """
    if cut <= 0 or cut >= len(ordered):
        return cut
    boundary_ts = ordered[COLS.timestamp].iloc[cut]
    ts = ordered[COLS.timestamp].to_numpy()
    # tiến tới hết khối cùng timestamp
    while cut < len(ordered) and ts[cut] == boundary_ts:
        cut += 1
    return cut


def temporal_split(df: pd.DataFrame, config: SamldConfig | None = None) -> TemporalSplit:
    """Chia train/val/test theo thứ tự thời gian, đảm bảo không leakage."""
    config = config or get_samld_config()
    ordered = df.sort_values(COLS.timestamp, kind="mergesort").reset_index(drop=True)
    n = len(ordered)

    train_cut = _cut_at_boundary(ordered, int(n * config.train_fraction))
    val_cut = _cut_at_boundary(ordered, int(n * (config.train_fraction + config.val_fraction)))
    if not (0 < train_cut < val_cut < n):
        raise ValueError(
            f"Chia thời gian rỗng: train_cut={train_cut}, val_cut={val_cut}, n={n}. "
            "Kiểm tra fraction hoặc phân bố thời gian."
        )

    train = ordered.iloc[:train_cut].reset_index(drop=True)
    val = ordered.iloc[train_cut:val_cut].reset_index(drop=True)
    test = ordered.iloc[val_cut:].reset_index(drop=True)

    split = TemporalSplit(
        train=train,
        val=val,
        test=test,
        train_end=train[COLS.timestamp].max(),
        val_end=val[COLS.timestamp].max(),
    )
    assert_temporal_order(split)
    logger.info(
        "SAML-D split thời gian: train=%d (≤%s), val=%d, test=%d (≥%s) | dương train/val/test=%.3f%%/%.3f%%/%.3f%%",
        len(train),
        split.train_end.date(),
        len(val),
        len(test),
        test[COLS.timestamp].min().date(),
        100 * train[COLS.label].mean(),
        100 * val[COLS.label].mean(),
        100 * test[COLS.label].mean(),
    )
    return split


def assert_temporal_order(split: TemporalSplit) -> None:
    """Bất biến chống rò rỉ: train < val < test theo thời gian, nghiêm ngặt."""
    tr_max = split.train[COLS.timestamp].max()
    va_min = split.val[COLS.timestamp].min()
    va_max = split.val[COLS.timestamp].max()
    te_min = split.test[COLS.timestamp].min()
    if not (tr_max < va_min):
        raise AssertionError(f"LEAKAGE: max(train)={tr_max} không < min(val)={va_min}.")
    if not (va_max < te_min):
        raise AssertionError(f"LEAKAGE: max(val)={va_max} không < min(test)={te_min}.")
