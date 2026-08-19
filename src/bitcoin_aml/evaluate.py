"""Đánh giá nhánh Bitcoin AML — báo cáo đúng chỉ số cho dữ liệu mất cân bằng.

Không báo Accuracy đơn lẻ: với ~2% illicit, một mô hình nói "tất cả licit" vẫn
đạt 98% accuracy. Lấy illicit làm lớp DƯƠNG và báo precision/recall/F1 của
illicit, ROC-AUC, PR-AUC (average precision), và ma trận nhầm lẫn.
"""

from __future__ import annotations

from typing import Any

from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

from src.bitcoin_aml.data import ILLICIT
from src.bitcoin_aml.model import illicit_probability


def evaluate_split(model, x, y_true, *, split_name: str) -> dict[str, Any]:  # noqa: ANN001
    """Chấm một tập; trả về khối chỉ số lấy từ mô hình THẬT, không hard-code."""
    scores = illicit_probability(model, x)
    y_pred = [ILLICIT if s >= 0.5 else 0 for s in scores]

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=[ILLICIT], average=None, zero_division=0
    )
    # ROC/PR-AUC cần cả hai lớp có mặt trong y_true.
    unique = set(int(v) for v in y_true)
    roc = float(roc_auc_score(y_true, scores)) if len(unique) > 1 else None
    pr = float(average_precision_score(y_true, scores)) if len(unique) > 1 else None
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, ILLICIT]).ravel()

    return {
        "split": split_name,
        "support_total": int(len(y_true)),
        "support_illicit": int(sum(1 for v in y_true if int(v) == ILLICIT)),
        "precision_illicit": float(precision[0]),
        "recall_illicit": float(recall[0]),
        "f1_illicit": float(f1[0]),
        "roc_auc": roc,
        "pr_auc": pr,
        "confusion_matrix": {
            "true_licit": {"pred_licit": int(tn), "pred_illicit": int(fp)},
            "true_illicit": {"pred_licit": int(fn), "pred_illicit": int(tp)},
        },
    }


#: Các mốc ngân sách cảnh báo để vẽ đường vận hành — cùng dạng với hai nhánh
#: kia, để thẻ nhánh trên giao diện đọc song song được.
BUDGET_STEPS = (100, 250, 500, 1000, 2500, 5000, 10000)


def budget_curve(scores: list[float], y_true: list[int]) -> list[dict[str, Any]]:
    """Với mỗi ngân sách cảnh báo, gắn cờ N giao dịch điểm cao nhất và đo lại.

    Trả về danh sách ``{alerts, caught, precision, recall}`` — đúng khuôn mà
    endpoint /fc/model-branches và thẻ nhánh trên giao diện đang dùng cho hai
    nhánh IBM và SAML-D.
    """
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    total_illicit = sum(1 for v in y_true if int(v) == ILLICIT) or 1
    points: list[dict[str, Any]] = []
    for budget in BUDGET_STEPS:
        if budget > len(order):
            break
        chosen = order[:budget]
        caught = sum(1 for i in chosen if int(y_true[i]) == ILLICIT)
        points.append(
            {
                "alerts": budget,
                "caught": int(caught),
                "precision": round(caught / budget, 6),
                "recall": round(caught / total_illicit, 6),
            }
        )
    return points
