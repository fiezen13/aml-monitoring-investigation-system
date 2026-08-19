"""Tầng dịch vụ — giữ một bộ suy luận đã nạp, dùng chung cho API.

Nạp mô hình là việc tốn kém (đọc joblib, dựng rừng), nên nạp một lần rồi cache
theo tiến trình. ``lru_cache`` đảm bảo mọi request dùng chung một đối tượng, và
có thể xoá cache khi cần nạp lại artifact mới.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from src.bitcoin_aml.inference import BitcoinAmlPredictor, ModelNotTrainedError

logger = logging.getLogger("fin07.bitcoin_aml.service")


@lru_cache(maxsize=1)
def get_predictor() -> BitcoinAmlPredictor:
    """Bộ suy luận dùng chung, nạp lần đầu khi được gọi.

    Ném ``ModelNotTrainedError`` nếu artifact chưa có — tầng API bắt và trả 503,
    để phân biệt rõ "chưa huấn luyện" với lỗi đầu vào của người dùng.
    """
    return BitcoinAmlPredictor()


def reset_predictor() -> None:
    """Xoá cache để lần gọi sau nạp lại artifact mới (sau khi huấn luyện lại)."""
    get_predictor.cache_clear()


def predictor_available() -> bool:
    """Đã có artifact để phục vụ chưa — dùng cho healthcheck/branch listing."""
    try:
        get_predictor()
        return True
    except ModelNotTrainedError:
        return False
