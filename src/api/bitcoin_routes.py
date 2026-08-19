"""API suy luận nhánh Bitcoin AML (Elliptic++).

Tách thành router riêng vì đây là một nhánh độc lập với các màn hình "Thành phố
tài chính" (fc_routes). Endpoint theo tiền tố ``/aml/bitcoin`` — không trộn vào
``/fc``.

Không huấn luyện ở đây. Nếu artifact chưa có, trả 503 để phân biệt rõ "chưa
huấn luyện mô hình" với lỗi đầu vào của người dùng (422).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.bitcoin_aml.inference import ModelNotTrainedError
from src.bitcoin_aml.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    BitcoinAmlResult,
    TransactionFeatures,
)
from src.bitcoin_aml.service import get_predictor

logger = logging.getLogger("fin07.api.bitcoin")

router = APIRouter()


def _predictor():  # noqa: ANN202 - kiểu nội bộ, trả BitcoinAmlPredictor
    try:
        return get_predictor()
    except ModelNotTrainedError as exc:
        # 503: dịch vụ chưa sẵn sàng vì thiếu artifact, không phải lỗi người dùng.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/aml/bitcoin/predict", response_model=BitcoinAmlResult)
async def predict_bitcoin(item: TransactionFeatures) -> BitcoinAmlResult:
    """Chấm một giao dịch Bitcoin, trả bằng chứng có cấu trúc cho tác tử.

    Vector ``features`` phải khớp đúng số lượng và thứ tự đặc trưng đã chốt lúc
    huấn luyện. Sai chiều → 422, không chấm bừa.
    """
    predictor = _predictor()
    try:
        return predictor.predict_one(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/aml/bitcoin/predict/batch", response_model=BatchPredictResponse)
async def predict_bitcoin_batch(request: BatchPredictRequest) -> BatchPredictResponse:
    """Chấm nhiều giao dịch trong một lượt (vector hoá, không lặp gọi mô hình)."""
    predictor = _predictor()
    try:
        results = predictor.predict_batch(request.transactions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BatchPredictResponse(
        model=predictor.model_name,
        model_id=predictor.model_id,
        count=len(results),
        results=results,
    )
