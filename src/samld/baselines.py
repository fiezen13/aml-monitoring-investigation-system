"""Baseline tabular cho SAML-D — Logistic Regression + XGBoost.

Chạy trên CHÍNH đặc trưng cạnh đã mã hoá của model đồ thị (không có thông tin
đồ thị), để so sánh công bằng "graph có thêm giá trị gì so với tabular thuần".
Không dùng nhãn làm đặc trưng (hàng rào rò rỉ đã ở tầng encoder).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger("fin07.samld.baselines")


@dataclass
class BaselineResult:
    name: str
    test_scores: np.ndarray
    train_seconds: float
    n_params: int | None = None


def _pos_weight(y: np.ndarray) -> float:
    pos = float(y.sum())
    neg = float(len(y) - pos)
    return neg / pos if pos else 1.0


def train_logreg(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> BaselineResult:
    started = time.perf_counter()
    model = LogisticRegression(max_iter=200, class_weight="balanced", n_jobs=-1)
    model.fit(x_train, y_train)
    scores = model.predict_proba(x_test)[:, 1]
    return BaselineResult(
        name="logistic_regression",
        test_scores=scores,
        train_seconds=time.perf_counter() - started,
        n_params=int(x_train.shape[1] + 1),
    )


def train_xgboost(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> BaselineResult:
    import xgboost as xgb

    started = time.perf_counter()
    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=_pos_weight(y_train),
        tree_method="hist",
        n_jobs=-1,
        eval_metric="aucpr",
    )
    model.fit(x_train, y_train)
    scores = model.predict_proba(x_test)[:, 1]
    return BaselineResult(
        name="xgboost",
        test_scores=scores,
        train_seconds=time.perf_counter() - started,
        n_params=int(model.get_booster().num_boosted_rounds()),
    )


def run_tabular_baselines(
    x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, *, include_xgboost: bool = True
) -> list[BaselineResult]:
    results = [train_logreg(x_train, y_train, x_test)]
    if include_xgboost:
        try:
            results.append(train_xgboost(x_train, y_train, x_test))
        except Exception as exc:  # OpenMP/thư viện thiếu ở môi trường cục bộ
            logger.warning("Bỏ qua XGBoost baseline: %s", exc)
    return results
