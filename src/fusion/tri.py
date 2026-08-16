"""Hợp nhất ba nhánh phát hiện — hộp 5 của sơ đồ kiến trúc.

``src/fusion/model.py`` hợp nhất hai nhánh (Isolation Forest + Graph) và đã được
đóng băng cùng bản phát hành v2. Module này **không sửa** nó; nó bổ sung nhánh
thứ ba — Rule — theo đúng phép toán ấy, mở rộng lên ba thành phần:

    contribution_i = weight_i × percentile_i
    fusion_score   = Σ contribution_i

Giữ nguyên phép toán là có chủ đích. ``get_risk_breakdown`` suy ngược trọng số
bằng ``contribution / percentile`` để giải thích điểm cho chuyên viên; đổi công
thức ở đây sẽ làm phần giải thích nói sai.

Hai điểm khác biệt so với bản hai nhánh:

* **Nhánh vắng mặt không giống nhánh bằng 0.** Isolation Forest và Graph chấm
  mọi tài khoản, nên phân vị luôn có. Nhánh Rule thì khác: không luật nào kích
  hoạt nghĩa là *đã kiểm và không thấy vi phạm* — đó là thông tin thật, phân vị
  bằng 0, chứ không phải thiếu dữ liệu. Chỉ khi một nhánh **không chạy được** ta
  mới coi là vắng mặt và chuẩn hoá lại trọng số trên các nhánh còn lại.
* **Tìm trọng số trên đơn hình hai chiều** thay vì quét một chiều.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

BRANCHES: tuple[str, ...] = ("rule", "isolation_forest", "graph")

TRI_BUNDLE_FORMAT = "fin07.rule_if_graph_fusion.v1"


@dataclass(frozen=True)
class TriWeights:
    """Trọng số đã chuẩn hoá của ba nhánh."""

    rule: float
    isolation_forest: float
    graph: float

    def as_dict(self) -> dict[str, float]:
        return {"rule": self.rule, "isolation_forest": self.isolation_forest, "graph": self.graph}

    def __post_init__(self) -> None:
        total = self.rule + self.isolation_forest + self.graph
        if not np.isclose(total, 1.0, atol=1e-9):
            raise ValueError(f"trọng số phải cộng lại bằng 1, nhận {total}")
        if min(self.rule, self.isolation_forest, self.graph) < 0:
            raise ValueError("trọng số không được âm")


def fuse(
    *,
    rule_percentile: np.ndarray,
    if_percentile: np.ndarray,
    graph_percentile: np.ndarray,
    weights: TriWeights,
) -> dict[str, np.ndarray]:
    """Hợp nhất ba phân vị thành một điểm, giữ lại đóng góp của từng nhánh.

    ``NaN`` nghĩa là nhánh đó **không chạy được** cho dòng này; trọng số của nó
    được chia lại cho các nhánh còn lại. Giá trị 0 là một phân vị hợp lệ và
    không kích hoạt cơ chế đó.
    """
    arrays = {
        "rule": np.asarray(rule_percentile, dtype=np.float64),
        "isolation_forest": np.asarray(if_percentile, dtype=np.float64),
        "graph": np.asarray(graph_percentile, dtype=np.float64),
    }
    sizes = {len(a) for a in arrays.values()}
    if len(sizes) != 1:
        raise ValueError("ba nhánh phải có cùng số dòng")

    w = weights.as_dict()
    available_weight = np.zeros(sizes.pop(), dtype=np.float64)
    for name, values in arrays.items():
        available_weight += np.where(np.isfinite(values), w[name], 0.0)
    # Không nhánh nào chạy được thì không có điểm để nói; giữ 1.0 để phép chia an
    # toàn, đóng góp vẫn bằng 0 vì mọi phân vị đều NaN.
    safe_weight = np.where(available_weight > 0, available_weight, 1.0)

    out: dict[str, np.ndarray] = {}
    total = np.zeros_like(safe_weight)
    for name, values in arrays.items():
        contribution = np.where(np.isfinite(values), w[name] * values / safe_weight, 0.0)
        out[f"{name}_contribution"] = contribution
        total += contribution

    out["fusion_score"] = np.clip(total, 0.0, 1.0)
    out["fusion_complete"] = available_weight > 0
    return out


def _f1(labels: np.ndarray, predicted: np.ndarray) -> float:
    true_positive = float(np.sum(predicted & (labels == 1)))
    if true_positive == 0:
        return 0.0
    precision = true_positive / float(np.sum(predicted))
    recall = true_positive / float(np.sum(labels == 1))
    return 2 * precision * recall / (precision + recall)


def best_threshold(scores: np.ndarray, labels: np.ndarray, *, quantiles: int = 200) -> tuple[float, float]:
    """Ngưỡng cho F1 cao nhất, dò trên phân vị của chính điểm số.

    Dò trên phân vị chứ không trên lưới đều: điểm hợp nhất dồn gần 0, lưới đều sẽ
    tiêu gần hết số lần thử vào vùng không có dữ liệu.
    """
    finite = scores[np.isfinite(scores)]
    if finite.size == 0:
        return 1.0, 0.0
    candidates = np.unique(np.quantile(finite, np.linspace(0.5, 1.0, quantiles)))
    best = (1.0, 0.0)
    for threshold in candidates:
        score = _f1(labels, scores >= threshold)
        if score > best[1]:
            best = (float(threshold), score)
    return best


def select_weights(
    *,
    rule_percentile: np.ndarray,
    if_percentile: np.ndarray,
    graph_percentile: np.ndarray,
    labels: np.ndarray,
    step: float = 0.05,
) -> tuple[TriWeights, float, float, list[dict[str, float]]]:
    """Chọn trọng số ba nhánh trên **tập kiểm định**, tối đa hoá F1.

    Quét đơn hình hai chiều với bước ``step``. Với bước 0,05 là 231 tổ hợp — đủ
    mịn để thấy dạng mặt lỗi mà vẫn chạy được trong vài phút trên vài triệu dòng.

    Trả về (trọng số, ngưỡng, F1, toàn bộ lưới) — lưới được giữ lại để báo cáo
    còn nói được vì sao tổ hợp này thắng.
    """
    labels = np.asarray(labels).astype(np.int8)
    grid: list[dict[str, float]] = []
    steps = int(round(1.0 / step))

    for i in range(steps + 1):
        for j in range(steps + 1 - i):
            rule_w = i * step
            if_w = j * step
            graph_w = round(1.0 - rule_w - if_w, 10)
            if graph_w < -1e-9:
                continue
            weights = TriWeights(rule=rule_w, isolation_forest=if_w, graph=max(graph_w, 0.0))
            fused = fuse(
                rule_percentile=rule_percentile,
                if_percentile=if_percentile,
                graph_percentile=graph_percentile,
                weights=weights,
            )
            threshold, f1 = best_threshold(fused["fusion_score"], labels)
            grid.append({**weights.as_dict(), "threshold": threshold, "f1": f1})

    # Hoà thì ưu tiên tổ hợp cân bằng hơn: một nhánh chiếm gần hết trọng số là
    # dấu hiệu hai nhánh kia không đóng góp gì, và bản hợp nhất khi đó chỉ là mô
    # hình đơn đội lốt.
    best = max(grid, key=lambda item: (item["f1"], -max(item[b] for b in BRANCHES)))
    weights = TriWeights(rule=best["rule"], isolation_forest=best["isolation_forest"], graph=best["graph"])
    return weights, float(best["threshold"]), float(best["f1"]), grid


def evaluate_at(
    *,
    scores: np.ndarray,
    labels: np.ndarray,
    threshold: float,
) -> dict[str, float | int]:
    """Số liệu tại một ngưỡng cố định — dùng cho tập kiểm tra."""
    labels = np.asarray(labels).astype(np.int8)
    predicted = scores >= threshold
    tp = int(np.sum(predicted & (labels == 1)))
    fp = int(np.sum(predicted & (labels == 0)))
    fn = int(np.sum(~predicted & (labels == 1)))
    tn = int(np.sum(~predicted & (labels == 0)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "rows": int(labels.size),
        "positives": int(np.sum(labels == 1)),
        "threshold": float(threshold),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "pr_auc": round(average_precision(scores, labels), 6),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "alerts": tp + fp,
        "alert_rate": round((tp + fp) / labels.size, 6) if labels.size else 0.0,
    }


def average_precision(scores: np.ndarray, labels: np.ndarray) -> float:
    """PR-AUC theo lối trung bình chính xác, không nội suy."""
    labels = np.asarray(labels).astype(np.int8)
    order = np.argsort(-np.asarray(scores, dtype=np.float64), kind="stable")
    ordered = labels[order]
    positives = float(np.sum(ordered == 1))
    if positives == 0:
        return 0.0
    cumulative_tp = np.cumsum(ordered == 1)
    precision_at_k = cumulative_tp / np.arange(1, ordered.size + 1)
    return float(np.sum(precision_at_k * (ordered == 1)) / positives)


def rank_percentile(values: Iterable[float]) -> np.ndarray:
    """Chuẩn hoá điểm thô thành phân vị 0–1 theo thứ hạng.

    Dùng cho nhánh Rule: điểm luật là thang 0–100 do con người đặt, không cùng
    đơn vị với phân vị đã hiệu chỉnh của hai nhánh kia. Đưa về thứ hạng để ba
    nhánh nói cùng một ngôn ngữ trước khi cộng.
    """
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return array
    order = np.argsort(array, kind="stable")
    ranks = np.empty(array.size, dtype=np.float64)
    ranks[order] = np.arange(array.size, dtype=np.float64)
    return ranks / max(array.size - 1, 1)


def build_bundle(
    *,
    fusion_version: str,
    weights: TriWeights,
    threshold: float,
    validation: dict[str, Any],
    test: dict[str, Any],
    provenance: dict[str, Any],
    grid: Sequence[dict[str, float]],
) -> dict[str, Any]:
    """Gói bản phát hành hợp nhất ba nhánh, dạng khai báo thuần."""
    return {
        "artifact_format": TRI_BUNDLE_FORMAT,
        "fusion_version": fusion_version,
        "window": "7d",
        "branches": list(BRANCHES),
        "score_semantics": "train-percentile weighted score; 1.0 = highest review priority",
        "missing_component_policy": "renormalize_available_weights",
        "weights": weights.as_dict(),
        "threshold": float(threshold),
        "validation": validation,
        "test": test,
        "weight_grid": [dict(item) for item in grid],
        "provenance": provenance,
    }
