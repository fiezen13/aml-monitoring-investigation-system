from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    auc,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)


def paper_binary_metrics(labels: np.ndarray, logits: np.ndarray) -> dict[str, object]:
    """Metrics used by the official MEGA-GNN edge-classification code.

    Its F1 uses argmax over two logits and its PR-AUC ranks the raw positive
    logit. We retain that behavior for table comparability, while FIN-07's
    operational arm separately uses calibrated softmax scores.
    """

    labels = np.asarray(labels, dtype=np.int64)
    logits = np.asarray(logits, dtype=np.float64)
    predictions = logits.argmax(axis=1)
    precision_curve, recall_curve, _ = precision_recall_curve(labels, logits[:, 1])
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "decision_rule": "argmax_two_logits",
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "pr_auc": float(auc(recall_curve, precision_curve)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "rows": int(labels.size),
        "positives": int(labels.sum()),
    }


def best_f1_threshold(labels: np.ndarray, scores: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    index = int(np.nanargmax(f1))
    if index >= len(thresholds):
        return 1.0
    return float(thresholds[index])


def binary_metrics(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    threshold: float = 0.5,
) -> dict[str, object]:
    labels = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    predictions = (scores >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "pr_auc": float(average_precision_score(labels, scores)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "rows": int(labels.size),
        "positives": int(labels.sum()),
    }


def budget_metrics(labels: np.ndarray, scores: np.ndarray, budgets: list[int]) -> list[dict]:
    order = np.argsort(-scores, kind="stable")
    ranked = labels[order]
    cumulative = np.cumsum(ranked)
    positives = int(labels.sum())
    rows: list[dict] = []
    for budget in budgets:
        if budget <= 0 or budget > labels.size:
            continue
        caught = int(cumulative[budget - 1])
        rows.append(
            {
                "alerts": budget,
                "caught": caught,
                "precision": caught / budget,
                "recall": caught / positives if positives else None,
            }
        )
    return rows
