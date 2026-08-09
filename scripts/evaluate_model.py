"""Tìm ngưỡng tối ưu trên Val (Recall>=80%, ít alert nhất); đánh giá trên Test."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

PROCESSED_DIR = Path("data/processed")
TARGET_RECALL = 0.80


def _account_labels_for_split(split: str, labels_path: Path) -> pd.Series:
    """y_true cấp account trong đúng split (join transaction_id → tránh rò nhãn liên-kỳ)."""
    tx_path = PROCESSED_DIR / f"transactions_{split}.parquet"
    tx = pl.scan_parquet(tx_path).select(
        ["transaction_id", "from_account_key", "to_account_key"]
    )
    lab = pl.scan_csv(labels_path).select(["transaction_id", "Is Laundering"])
    joined = (
        tx.join(lab, on="transaction_id", how="left")
        .with_columns(pl.col("Is Laundering").fill_null(0).cast(pl.Int8))
        .collect()
    )
    pos = joined.filter(pl.col("Is Laundering") == 1)
    pos_acc = pl.concat(
        [
            pos.select(pl.col("from_account_key").alias("account_key")),
            pos.select(pl.col("to_account_key").alias("account_key")),
        ]
    ).unique()

    all_acc = pl.concat(
        [
            joined.select(pl.col("from_account_key").alias("account_key")),
            joined.select(pl.col("to_account_key").alias("account_key")),
        ]
    ).unique()

    mapped = (
        all_acc.join(pos_acc.with_columns(pl.lit(1).alias("y_true")), on="account_key", how="left")
        .with_columns(pl.col("y_true").fill_null(0).cast(pl.Int8))
        .to_pandas()
    )
    return mapped.set_index("account_key")["y_true"]


def _join_scored_labels(scored_path: Path, y_account: pd.Series) -> pd.DataFrame:
    df = pd.read_csv(scored_path)
    df["y_true"] = df["account_key"].map(y_account).fillna(0).astype(int)
    return df


def _find_best_threshold(y_true: np.ndarray, scores: np.ndarray, target_recall: float) -> float:
    """Recall >= target tại số alert (positive preds) nhỏ nhất."""
    uniq = np.unique(scores)
    if len(uniq) > 2000:
        cand = np.unique(np.percentile(scores, np.linspace(0, 100, 2001)))
    else:
        cand = uniq

    best_thresh = float(cand.min()) if len(cand) else 0.0
    best_alerts = len(scores) + 1
    found = False

    for thr in np.sort(cand)[::-1]:
        y_pred = (scores >= thr).astype(int)
        alerts = int(y_pred.sum())
        if alerts == 0:
            continue
        rec = recall_score(y_true, y_pred, zero_division=0)
        if rec >= target_recall and alerts < best_alerts:
            best_alerts = alerts
            best_thresh = float(thr)
            found = True

    if not found:
        print(
            f"⚠️ Không tìm được ngưỡng đạt Recall>={target_recall:.0%}. "
            "Chọn ngưỡng có Recall cao nhất (ít alert nhất)."
        )
        best_rec = -1.0
        for thr in np.sort(cand)[::-1]:
            y_pred = (scores >= thr).astype(int)
            alerts = int(y_pred.sum())
            rec = recall_score(y_true, y_pred, zero_division=0)
            if rec > best_rec or (rec == best_rec and alerts < best_alerts):
                best_rec = rec
                best_alerts = alerts
                best_thresh = float(thr)

    return best_thresh


def _metrics(y_true: np.ndarray, scores: np.ndarray, thr: float) -> dict:
    y_pred = (scores >= thr).astype(int)
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    out = {
        "threshold": thr,
        "n": len(y_true),
        "n_pos": int(y_true.sum()),
        "n_alerts": int(y_pred.sum()),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "fpr": float(fpr),
    }
    if len(np.unique(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
        out["pr_auc"] = float(average_precision_score(y_true, scores))
    else:
        out["roc_auc"] = float("nan")
        out["pr_auc"] = float("nan")
    return out


def _fmt_row(name: str, value: str) -> str:
    return f"{name:<18} {value:>14}"


def _print_table(title: str, m: dict) -> None:
    # ASCII-only + flush: PowerShell đôi khi nuốt dòng Unicode/emoji
    lines = [
        "",
        "=" * 64,
        title,
        "=" * 64,
        _fmt_row("Metric", "Value"),
        "-" * 34,
        _fmt_row("Threshold", f"{m['threshold']:.4f}"),
        _fmt_row("N accounts", str(int(m["n"]))),
        _fmt_row("N positive", str(int(m["n_pos"]))),
        _fmt_row("N alerts", str(int(m["n_alerts"]))),
        _fmt_row("ROC-AUC", f"{m['roc_auc']:.4f}"),
        _fmt_row("PR-AUC", f"{m['pr_auc']:.4f}"),
        _fmt_row("Precision", f"{m['precision']:.4f}"),
        _fmt_row("Recall", f"{m['recall']:.4f}"),
        _fmt_row("F1-Score", f"{m['f1']:.4f}"),
        _fmt_row("FPR", f"{m['fpr']:.4f}"),
        "=" * 64,
        "",
    ]
    text = "\n".join(lines)
    print(text, flush=True)
    return text


def evaluate_model() -> None:
    labels_path = PROCESSED_DIR / "labels.csv"
    val_path = PROCESSED_DIR / "scored_val.csv"
    test_path = PROCESSED_DIR / "scored_test.csv"
    for p in (labels_path, val_path, test_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Missing {p}. Run ingest -> extract -> train first!"
            )

    print("[1/3] Join scored_val with labels.csv ...", flush=True)
    y_val_acc = _account_labels_for_split("val", labels_path)
    val = _join_scored_labels(val_path, y_val_acc)
    y_val = val["y_true"].to_numpy()
    s_val = val["risk_score"].to_numpy(dtype=float)

    print(
        f"[2/3] Search best_thresh on VAL (Recall>={TARGET_RECALL:.0%}, min alerts)...",
        flush=True,
    )
    best_thresh = _find_best_threshold(y_val, s_val, TARGET_RECALL)
    val_m = _metrics(y_val, s_val, best_thresh)
    val_text = _print_table(
        f"VALIDATION @ best_thresh (target Recall>={TARGET_RECALL:.0%})", val_m
    )

    print("[3/3] Apply best_thresh on TEST ...", flush=True)
    y_test_acc = _account_labels_for_split("test", labels_path)
    test = _join_scored_labels(test_path, y_test_acc)
    test_m = _metrics(
        test["y_true"].to_numpy(),
        test["risk_score"].to_numpy(dtype=float),
        best_thresh,
    )
    test_text = _print_table(f"TEST @ best_thresh={best_thresh:.4f}", test_m)

    thr_path = PROCESSED_DIR / "best_threshold.txt"
    thr_path.write_text(f"{best_thresh}\n", encoding="utf-8")
    report_path = PROCESSED_DIR / "evaluation_report.txt"
    report_path.write_text(
        f"best_thresh={best_thresh}\n{val_text}\n{test_text}\n", encoding="utf-8"
    )
    print(f"best_thresh -> {thr_path}", flush=True)
    print(f"report      -> {report_path}", flush=True)
    print("EVALUATION DONE", flush=True)


if __name__ == "__main__":
    evaluate_model()
