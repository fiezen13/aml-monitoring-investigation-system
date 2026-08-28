"""Đánh giá + phân tích AML cho nhánh SAML-D.

Vận hành trên DỰ ĐOÁN của tập test (labels + scores) ghép với metadata giao dịch
(cross_border, typology, quốc gia). Ngưỡng luôn chọn trên VALIDATION, áp cho test
đúng một lần. Typology chỉ dùng ở đây (đánh giá), không bao giờ ở inference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    fbeta_score,
    matthews_corrcoef,
    precision_recall_curve,
    roc_auc_score,
)

logger = logging.getLogger("fin07.samld.evaluate")


def extended_metrics(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float | dict]:
    """Bộ chỉ số đầy đủ cho AML mất cân bằng — KHÔNG lấy accuracy làm chính."""
    labels = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    pred = (scores >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, pred, labels=[0, 1]).ravel()
    pos = tp + fn
    neg = tn + fp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / pos if pos else 0.0
    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(fbeta_score(labels, pred, beta=1, zero_division=0)),
        "f2": float(fbeta_score(labels, pred, beta=2, zero_division=0)),
        "pr_auc": float(average_precision_score(labels, scores)) if pos else 0.0,
        "roc_auc": float(roc_auc_score(labels, scores)) if pos and neg else 0.0,
        "mcc": float(matthews_corrcoef(labels, pred)) if (pos and neg) else 0.0,
        "balanced_accuracy": float(balanced_accuracy_score(labels, pred)) if (pos and neg) else 0.0,
        "fpr": float(fp / neg) if neg else 0.0,  # tỉ lệ dương giả trên nhóm âm
        "fnr": float(fn / pos) if pos else 0.0,  # tỉ lệ bỏ sót trên nhóm dương
        "brier": float(brier_score_loss(labels, scores)) if pos else 0.0,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "rows": int(labels.size),
        "positives": int(pos),
    }


def select_threshold(
    val_labels: np.ndarray, val_scores: np.ndarray, *, strategy: str = "f1", recall_target: float = 0.90
) -> float:
    """Chọn ngưỡng TRÊN VALIDATION. Không bao giờ nhìn test."""
    precision, recall, thresholds = precision_recall_curve(val_labels, val_scores)
    # precision_recall_curve trả len(thresholds) = len(precision)-1
    p, r, t = precision[:-1], recall[:-1], thresholds
    if len(t) == 0:
        return 0.5
    if strategy == "recall_target":
        ok = np.where(r >= recall_target)[0]
        # trong các ngưỡng đạt recall mục tiêu, lấy cái precision cao nhất
        return float(t[ok[np.argmax(p[ok])]]) if len(ok) else float(t[np.argmax(r)])
    beta = 2.0 if strategy == "f2" else 1.0
    fbeta = (1 + beta**2) * p * r / np.maximum(beta**2 * p + r, 1e-12)
    return float(t[int(np.nanargmax(fbeta))])


@dataclass
class TestFrame:
    """Dự đoán test ghép metadata — nguồn cho mọi phân tích."""

    df: pd.DataFrame  # cột: label, score, cross_border, typology, sender_country, receiver_country

    @classmethod
    def from_predictions(cls, predictions: pd.DataFrame, test_meta: pd.DataFrame) -> TestFrame:
        """Ghép predictions (source_edge_id) với metadata (transaction_id)."""
        meta = test_meta.copy()
        meta["transaction_id"] = meta["transaction_id"].astype(np.int64)
        # KHÔNG lấy "label" từ meta — nhãn đã có trong predictions (is_laundering).
        # Lấy cả hai sẽ tạo hai cột "label" và làm hỏng các phép tính chỉ số.
        merged = predictions.merge(
            meta[["transaction_id", "cross_border", "typology", "sender_country", "receiver_country"]],
            left_on="source_edge_id",
            right_on="transaction_id",
            how="left",
        )
        merged = merged.rename(columns={"is_laundering": "label"})
        return cls(df=merged)


def subset_metrics(tf: TestFrame, mask: np.ndarray, threshold: float, *, name: str) -> dict:
    """Chỉ số trên một nhóm con (vd cross-border vs domestic) + tỉ lệ dương."""
    sub = tf.df[mask]
    m = extended_metrics(sub["label"].to_numpy(), sub["score"].to_numpy(), threshold)
    m["subset"] = name
    m["count"] = int(len(sub))
    m["laundering_prevalence"] = float(sub["label"].mean()) if len(sub) else 0.0
    return m


def cross_border_breakdown(tf: TestFrame, threshold: float) -> list[dict]:
    """Domestic vs cross-border — báo cáo RIÊNG, không kết luận xb = đáng ngờ."""
    xb = tf.df["cross_border"].to_numpy() > 0.5
    return [
        subset_metrics(tf, ~xb, threshold, name="domestic"),
        subset_metrics(tf, xb, threshold, name="cross_border"),
    ]


def per_typology(tf: TestFrame, threshold: float) -> list[dict]:
    """Recall theo TỪNG typology (chỉ trên nhãn dương). Typology = ground truth."""
    pos = tf.df[tf.df["label"] == 1]
    rows: list[dict] = []
    for typ, grp in pos.groupby("typology"):
        pred_pos = grp["score"].to_numpy() >= threshold
        support = int(len(grp))
        tp = int(pred_pos.sum())
        rows.append(
            {
                "typology": str(typ),
                "support": support,
                "tp": tp,
                "fn": support - tp,
                "recall": tp / support if support else 0.0,
                "mean_predicted_prob": float(grp["score"].mean()),
            }
        )
    return sorted(rows, key=lambda r: -r["support"])


def country_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Phân bố giao dịch/laundering theo quốc gia người gửi — CHẨN ĐOÁN, không phải điểm rủi ro FATF."""
    g = df.groupby("sender_country").agg(
        transaction_count=("label", "size"),
        laundering_count=("label", "sum"),
    )
    g["laundering_rate"] = g["laundering_count"] / g["transaction_count"]
    return g.sort_values("laundering_rate", ascending=False).reset_index()
