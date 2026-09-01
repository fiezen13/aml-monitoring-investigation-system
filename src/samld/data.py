"""Nạp SAML-D thô, quy về lược đồ canonical, dẫn xuất đặc trưng, kiểm tính toàn vẹn.

KHÔNG chạm nhãn vào đặc trưng: ``label``/``typology`` chỉ đi kèm để đánh giá, và
được tách khỏi ma trận đặc trưng ở tầng graph/baseline. Country chỉ là ngữ cảnh
categorical của cạnh — không có danh sách quốc gia rủi ro cứng nào ở đây.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.samld.config import SamldConfig, get_samld_config
from src.samld.schema import COLS, RAW_TO_CANONICAL

logger = logging.getLogger("fin07.samld.data")


class SamldDataError(Exception):
    """Dữ liệu SAML-D thiếu cột hoặc sai định dạng không thể tiếp tục."""


def _derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Dẫn xuất đặc trưng cạnh HỢP LỆ từ các trường giao dịch (không đụng nhãn)."""
    out = df.copy()

    # Mốc thời gian đầy đủ từ ngày + giờ trong ngày.
    out[COLS.timestamp] = pd.to_datetime(out[COLS.date].astype(str) + " " + out[COLS.time].astype(str), errors="coerce")

    # Số tiền: log1p để nén đuôi nặng; giữ cả bản gốc cho evidence/hiển thị.
    amount = pd.to_numeric(out[COLS.amount], errors="coerce")
    out["amount_log"] = np.log1p(amount.clip(lower=0))

    ts = out[COLS.timestamp]
    out["hour"] = ts.dt.hour.astype("float32")
    out["day_of_week"] = ts.dt.dayofweek.astype("float32")
    out["day_of_month"] = ts.dt.day.astype("float32")
    origin = ts.min()
    out["elapsed_days"] = ((ts - origin).dt.total_seconds() / 86400.0).astype("float32")

    # Ngữ cảnh — KHÔNG phải nhãn rủi ro. cross_border = hai quốc gia khác nhau.
    out["cross_border"] = (out[COLS.sender_country] != out[COLS.receiver_country]).astype("float32")
    out["currency_mismatch"] = (out[COLS.payment_currency] != out[COLS.received_currency]).astype("float32")

    return out


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    """Kiểm tra toàn vẹn; loại dòng hỏng nhưng GHI LOG, không bỏ im lặng."""
    n0 = len(df)
    bad_account = df[COLS.sender_account].isna() | df[COLS.receiver_account].isna()
    bad_amount = pd.to_numeric(df[COLS.amount], errors="coerce").fillna(-1) <= 0
    bad_label = ~df[COLS.label].isin([0, 1])
    bad_time = df[COLS.timestamp].isna()
    bad = bad_account | bad_amount | bad_label | bad_time
    if bad.any():
        logger.warning(
            "SAML-D: loại %d/%d dòng hỏng (tài khoản rỗng=%d, amount<=0=%d, nhãn lạ=%d, thời gian lỗi=%d)",
            int(bad.sum()),
            n0,
            int(bad_account.sum()),
            int(bad_amount.sum()),
            int(bad_label.sum()),
            int(bad_time.sum()),
        )
    clean = df[~bad].reset_index(drop=True)
    if clean.empty:
        raise SamldDataError("Sau khi kiểm tra, không còn dòng SAML-D hợp lệ nào.")
    return clean


def load_samld(config: SamldConfig | None = None) -> pd.DataFrame:
    """Nạp + canonical + dẫn xuất + kiểm tra. Trả DataFrame đã sẵn cho split/graph.

    Cột trả về: canonical (sender/receiver_account, amount, currency, country,
    payment_type, label, typology, timestamp) + đặc trưng dẫn xuất (amount_log,
    hour, day_of_week, day_of_month, elapsed_days, cross_border, currency_mismatch).
    """
    config = config or get_samld_config()
    if not config.raw_csv.exists():
        raise SamldDataError(f"Không thấy {config.raw_csv}. Đặt SAML-D.csv vào gốc repo hoặc trỏ SAMLD_RAW_CSV.")

    logger.info("Nạp SAML-D từ %s …", config.raw_csv)
    raw = pd.read_csv(config.raw_csv)
    missing = set(RAW_TO_CANONICAL) - set(raw.columns)
    if missing:
        raise SamldDataError(f"SAML-D thiếu cột {sorted(missing)}. Cột thực tế: {list(raw.columns)}.")
    df = raw[list(RAW_TO_CANONICAL)].rename(columns=RAW_TO_CANONICAL)
    df[COLS.label] = pd.to_numeric(df[COLS.label], errors="coerce")

    df = _derive_features(df)
    df = _validate(df)

    # Mã giao dịch ổn định để đối chiếu evidence sau này. Không phải đặc trưng.
    df.insert(0, "transaction_id", df.index.astype(str))
    logger.info(
        "SAML-D sẵn sàng: %d giao dịch, %d nhãn dương (%.3f%%), %d tài khoản.",
        len(df),
        int(df[COLS.label].sum()),
        100 * df[COLS.label].mean(),
        pd.concat([df[COLS.sender_account], df[COLS.receiver_account]]).nunique(),
    )
    return df
