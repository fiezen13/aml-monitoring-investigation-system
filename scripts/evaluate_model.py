"""Evaluate Isolation Forest scores: best_thresh tren Val, bao cao tren Test.

Ví dụ:
  python scripts/evaluate_model.py
  python scripts/evaluate_model.py --precision-at-k 50,100,500,1000
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

PROCESSED_DIR = Path("data/processed")
DB_PATH = Path("data/processed/aml.duckdb")
SCORES_PATH = PROCESSED_DIR / "if_scores_v1.parquet"
REPORT_PATH = PROCESSED_DIR / "evaluation_report.txt"
TARGET_RECALL = 0.80
WINDOW_DAYS = {"1d": 1, "7d": 7, "14d": 14}
DEFAULT_PRECISION_AT_K = (50, 100, 500, 1000)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate IF scores vs label_laundering")
    p.add_argument("--scores", default=str(SCORES_PATH))
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--window", default="7d", choices=tuple(WINDOW_DAYS))
    p.add_argument("--report", default=str(REPORT_PATH))
    p.add_argument("--target-recall", type=float, default=TARGET_RECALL)
    p.add_argument(
        "--subject-accounts",
        default=None,
        help="Manifest tai khoan co lich su day du; chi danh gia nhung tai khoan nay",
    )
    p.add_argument(
        "--precision-at-k",
        default=",".join(str(k) for k in DEFAULT_PRECISION_AT_K),
        help="Danh sach K cho Precision@K (vd 50,100,500,1000)",
    )
    return p.parse_args()


def _parse_ks(raw: str) -> tuple[int, ...]:
    ks: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        k = int(part)
        if k <= 0:
            raise ValueError(f"K phai > 0, nhan duoc {k}")
        ks.append(k)
    if not ks:
        raise ValueError("Can it nhat 1 gia tri K cho --precision-at-k")
    return tuple(ks)


def _attach_split(scores: pd.DataFrame, window: str) -> pd.DataFrame:
    """Gan split bang join features_{split}_{window}.parquet (account_key, as_of_ts)."""
    parts: list[pd.DataFrame] = []
    for split in ("train", "val", "test"):
        path = PROCESSED_DIR / f"features_{split}_{window}.parquet"
        if not path.exists():
            continue
        keys = pd.read_parquet(path, columns=["account_key", "as_of_ts"])
        keys = keys.drop_duplicates()
        keys["split"] = split
        parts.append(keys)
    if not parts:
        raise FileNotFoundError(f"Khong tim thay features_*_{window}.parquet de gan split.")
    key_map = pd.concat(parts, ignore_index=True)
    scores = scores.copy()
    scores["as_of_ts"] = pd.to_datetime(scores["as_of_ts"], utc=True)
    key_map["as_of_ts"] = pd.to_datetime(key_map["as_of_ts"], utc=True)
    merged = scores.merge(key_map, on=["account_key", "as_of_ts"], how="left")
    missing = int(merged["split"].isna().sum())
    if missing:
        print(f"[warn] {missing:,} hang score khong map duoc split (bo qua khi evaluate).")
    return merged


def _window_labels_from_duckdb(samples: pd.DataFrame, db_path: Path, window_days: int) -> pd.DataFrame:
    """y_true theo handoff §4: laundering TX trong (as_of - window, as_of]."""
    if not db_path.exists():
        raise FileNotFoundError(f"Khong tim thay DuckDB: {db_path}")

    keys = samples[["account_key", "as_of_ts"]].drop_duplicates().copy()
    keys["as_of_ts"] = pd.to_datetime(keys["as_of_ts"], utc=True)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.register("eval_samples", keys)
        df = con.execute(
            f"""
            WITH sides AS (
                SELECT
                    from_account_key AS account_key,
                    occurred_at,
                    label_laundering
                FROM transaction
                WHERE from_account_key IS NOT NULL
                UNION ALL
                SELECT
                    to_account_key AS account_key,
                    occurred_at,
                    label_laundering
                FROM transaction
                WHERE to_account_key IS NOT NULL
            )
            SELECT
                s.account_key,
                s.as_of_ts,
                CAST(
                    MAX(
                        CASE
                            WHEN t.label_laundering = 1 THEN 1
                            ELSE 0
                        END
                    ) AS INTEGER
                ) AS y_true
            FROM eval_samples s
            LEFT JOIN sides t
              ON t.account_key = s.account_key
             AND t.occurred_at > s.as_of_ts - INTERVAL {int(window_days)} DAY
             AND t.occurred_at <= s.as_of_ts
            GROUP BY s.account_key, s.as_of_ts
            """
        ).fetchdf()
    finally:
        con.close()

    df["as_of_ts"] = pd.to_datetime(df["as_of_ts"], utc=True)
    df["y_true"] = df["y_true"].fillna(0).astype(int)
    return df


def _find_best_threshold(y_true: np.ndarray, scores: np.ndarray, target_recall: float) -> float:
    """argmin #alerts s.t. Recall >= target; fallback max recall."""
    uniq = np.unique(scores)
    if len(uniq) > 2500:
        cand = np.unique(np.percentile(scores, np.linspace(0, 100, 2501)))
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
        print(f"[warn] Khong dat Recall>={target_recall:.0%}. Chon nguong Recall cao nhat (it alert nhat).")
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


def _precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Ty le positive trong top-K theo anomaly_score giam dan."""
    n = len(scores)
    if n == 0 or k <= 0:
        return float("nan")
    kk = min(int(k), n)
    order = np.argsort(-scores, kind="mergesort")[:kk]
    return float(y_true[order].mean())


def _metrics(
    y_true: np.ndarray,
    scores: np.ndarray,
    thr: float,
    ks: tuple[int, ...],
) -> dict:
    y_pred = (scores >= thr).astype(int)
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    out: dict = {
        "threshold": float(thr),
        "n_accounts": int(len(y_true)),
        "n_positive": int(y_true.sum()),
        "n_alerts": int(y_pred.sum()),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "fpr": float(fpr),
        "precision_at_k": {int(k): _precision_at_k(y_true, scores, int(k)) for k in ks},
    }
    if len(np.unique(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
        out["pr_auc"] = float(average_precision_score(y_true, scores))
    else:
        out["roc_auc"] = float("nan")
        out["pr_auc"] = float("nan")
    return out


def _format_block(title: str, m: dict) -> str:
    lines = [
        "",
        "=" * 64,
        title,
        "=" * 64,
        f"{'Metric':<18} {'Value':>14}",
        "-" * 34,
        f"{'Threshold':<18} {m['threshold']:>14.4f}",
        f"{'N accounts':<18} {m['n_accounts']:>14d}",
        f"{'N positive':<18} {m['n_positive']:>14d}",
        f"{'N alerts':<18} {m['n_alerts']:>14d}",
        f"{'Precision':<18} {m['precision']:>14.4f}",
        f"{'Recall':<18} {m['recall']:>14.4f}",
        f"{'F1-Score':<18} {m['f1']:>14.4f}",
        f"{'ROC-AUC':<18} {m['roc_auc']:>14.4f}",
        f"{'PR-AUC':<18} {m['pr_auc']:>14.4f}",
        f"{'FPR':<18} {m['fpr']:>14.4f}",
    ]
    for k, v in m["precision_at_k"].items():
        lines.append(f"{f'Precision@{k}':<18} {v:>14.4f}")
    lines.extend(["=" * 64, ""])
    return "\n".join(lines)


def evaluate_model(
    scores_path: Path,
    db_path: Path,
    window: str,
    report_path: Path,
    target_recall: float,
    precision_at_k: tuple[int, ...],
    subject_accounts: Path | None = None,
) -> None:
    if not scores_path.exists():
        raise FileNotFoundError(f"Thieu {scores_path}. Chay generate_scores.py truoc.")

    window_days = WINDOW_DAYS[window]

    print("[1/4] Doc if_scores_v1.parquet ...", flush=True)
    scores = pd.read_parquet(scores_path, columns=["account_key", "as_of_ts", "window", "anomaly_score"])
    scores = _attach_split(scores, window)
    if subject_accounts is not None:
        # Counterparties appear in the batch only for the rows that touch a
        # subject, so their feature vectors describe that fragment. The
        # operational run does not score them; a benchmark that does is not
        # measuring the same system.
        subjects = {line.strip() for line in subject_accounts.read_text(encoding="utf-8").splitlines() if line.strip()}
        if not subjects:
            raise ValueError(f"File --subject-accounts rong: {subject_accounts}")
        before = len(scores)
        scores = scores[scores["account_key"].isin(subjects)].copy()
        if scores.empty:
            raise RuntimeError("Khong co tai khoan nao trong scores khop --subject-accounts")
        print(f"       loc theo subject: {before:,} -> {len(scores):,} dong", flush=True)

    print(
        f"[2/4] Gan nhan window-strict (laundering trong (as_of-{window}, as_of]) ...",
        flush=True,
    )
    labels = _window_labels_from_duckdb(scores, db_path, window_days)
    scored = scores.merge(labels, on=["account_key", "as_of_ts"], how="left")
    scored["y_true"] = scored["y_true"].fillna(0).astype(int)

    val = scored[scored["split"] == "val"].copy()
    test = scored[scored["split"] == "test"].copy()
    if val.empty or test.empty:
        raise RuntimeError(
            f"Val/Test rong sau join (val={len(val)}, test={len(test)}). Kiem tra features_* parquet va scores."
        )

    print(
        f"[3/4] Tim best_thresh tren VAL (Recall>={target_recall:.0%}, min alerts) ...",
        flush=True,
    )
    y_val = val["y_true"].to_numpy()
    s_val = val["anomaly_score"].to_numpy(dtype=float)
    best_thresh = _find_best_threshold(y_val, s_val, target_recall)
    val_m = _metrics(y_val, s_val, best_thresh, precision_at_k)

    print("[4/4] Ap dung best_thresh len TEST + Precision@K ...", flush=True)
    test_m = _metrics(
        test["y_true"].to_numpy(),
        test["anomaly_score"].to_numpy(dtype=float),
        best_thresh,
        precision_at_k,
    )

    val_text = _format_block(f"VALIDATION @ best_thresh (target Recall>={target_recall:.0%})", val_m)
    test_text = _format_block(f"TEST @ best_thresh={best_thresh:.4f}", test_m)
    report = (
        f"best_thresh={best_thresh}\n"
        f"scores={scores_path}\n"
        f"model_window={window}\n"
        f"label_def=window_strict (as_of - {window}, as_of]\n"
        f"precision_at_k={list(precision_at_k)}\n"
        f"{val_text}\n{test_text}\n"
    )
    print(report, flush=True)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    thr_path = PROCESSED_DIR / "best_threshold.txt"
    thr_path.write_text(f"{best_thresh}\n", encoding="utf-8")
    print(f"report -> {report_path}", flush=True)
    print(f"best_thresh -> {thr_path}", flush=True)
    print("EVALUATION DONE", flush=True)


def main() -> None:
    args = _parse_args()
    evaluate_model(
        scores_path=Path(args.scores),
        db_path=Path(args.db),
        window=args.window,
        report_path=Path(args.report),
        target_recall=args.target_recall,
        precision_at_k=_parse_ks(args.precision_at_k),
        subject_accounts=Path(args.subject_accounts) if args.subject_accounts else None,
    )


if __name__ == "__main__":
    main()
