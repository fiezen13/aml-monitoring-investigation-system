"""Đồ thị đánh giá SAML-D — PR / ROC / threshold / confusion / calibration.

PR curve quan trọng hơn ROC với dữ liệu mất cân bằng nặng. Dùng backend Agg
(không cần màn hình). Không hard-code màu theo quy ước riêng.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    ConfusionMatrixDisplay,
    precision_recall_curve,
    roc_curve,
)


def save_pr_curve(labels: np.ndarray, scores: np.ndarray, path: Path) -> None:
    precision, recall, _ = precision_recall_curve(labels, scores)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(recall, precision)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision–Recall (SAML-D test)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_roc_curve(labels: np.ndarray, scores: np.ndarray, path: Path) -> None:
    fpr, tpr, _ = roc_curve(labels, scores)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(fpr, tpr)
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=0.8)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC (SAML-D test)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_threshold_curve(labels: np.ndarray, scores: np.ndarray, path: Path) -> None:
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    p, r, t = precision[:-1], recall[:-1], thresholds
    f1 = 2 * p * r / np.maximum(p + r, 1e-12)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(t, p, label="Precision")
    ax.plot(t, r, label="Recall")
    ax.plot(t, f1, label="F1")
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Score")
    ax.set_title("Metrics vs threshold (SAML-D test)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_confusion_matrix(labels: np.ndarray, scores: np.ndarray, threshold: float, path: Path) -> None:
    pred = (np.asarray(scores) >= threshold).astype(int)
    fig, ax = plt.subplots(figsize=(4, 4))
    ConfusionMatrixDisplay.from_predictions(labels, pred, labels=[0, 1], ax=ax, colorbar=False)
    ax.set_title("Confusion matrix (SAML-D test)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_calibration_curve(labels: np.ndarray, scores: np.ndarray, path: Path) -> None:
    frac_pos, mean_pred = calibration_curve(labels, scores, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(mean_pred, frac_pos, marker="o")
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=0.8)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_title("Calibration (SAML-D test)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_all(labels: np.ndarray, scores: np.ndarray, threshold: float, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    save_pr_curve(labels, scores, out_dir / "precision_recall_curve.png")
    save_roc_curve(labels, scores, out_dir / "roc_curve.png")
    save_threshold_curve(labels, scores, out_dir / "threshold_curve.png")
    save_confusion_matrix(labels, scores, threshold, out_dir / "confusion_matrix.png")
    try:
        save_calibration_curve(labels, scores, out_dir / "calibration_curve.png")
    except Exception as exc:  # calibration cần đủ điểm mỗi bin
        return [f"calibration bỏ qua: {exc}"]
    return []
