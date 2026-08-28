"""Nhánh thí nghiệm ablation địa lý cho SAML-D (§18).

Mục đích: xem model học HÀNH VI giao dịch/mạng lưới hay bám vào tương quan địa lý
do bộ sinh tổng hợp tạo ra. Bốn nhánh:

* full          — đủ đặc trưng (quốc gia + cross_border).
* no_country    — bỏ thông tin quốc gia, GIỮ cross_border.
* no_geography  — bỏ cả quốc gia và cross_border.
* country_shuffle — xáo trộn quốc gia trong TRAIN (giữ đặc trưng khác), phá tương
                    quan địa lý mà không đổi phân phối biên.

Thao tác trên bản sao của split; không đụng dữ liệu gốc.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.samld.schema import COLS
from src.samld.split import TemporalSplit

ARMS = ("full", "no_country", "no_geography", "country_shuffle")
_MASK = "__MASKED__"


def _mask_country(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out[COLS.sender_country] = _MASK
    out[COLS.receiver_country] = _MASK
    return out


def apply_arm(split: TemporalSplit, arm: str, *, seed: int = 42) -> TemporalSplit:
    """Trả về split đã biến đổi theo nhánh ablation."""
    if arm == "full":
        return split
    if arm == "no_country":
        return TemporalSplit(
            train=_mask_country(split.train),
            val=_mask_country(split.val),
            test=_mask_country(split.test),
            train_end=split.train_end,
            val_end=split.val_end,
        )
    if arm == "no_geography":

        def strip(df: pd.DataFrame) -> pd.DataFrame:
            out = _mask_country(df)
            out["cross_border"] = 0.0  # bỏ luôn cờ xuyên biên giới
            return out

        return TemporalSplit(
            train=strip(split.train),
            val=strip(split.val),
            test=strip(split.test),
            train_end=split.train_end,
            val_end=split.val_end,
        )
    if arm == "country_shuffle":
        rng = np.random.default_rng(seed)
        train = split.train.copy()
        # Xáo trộn CẶP (sender, receiver) cùng nhau để giữ tính nhất quán nội tại,
        # chỉ phá liên kết địa lý ↔ nhãn. Chỉ trên TRAIN.
        perm = rng.permutation(len(train))
        train[COLS.sender_country] = train[COLS.sender_country].to_numpy()[perm]
        train[COLS.receiver_country] = train[COLS.receiver_country].to_numpy()[perm]
        return TemporalSplit(
            train=train,
            val=split.val,
            test=split.test,
            train_end=split.train_end,
            val_end=split.val_end,
        )
    raise ValueError(f"Nhánh ablation lạ: {arm}. Hợp lệ: {ARMS}")
