"""Fit Isolation Forest trên 20 đặc trưng hành vi (FIN-07 / feature_spec.md).

Ví dụ:
  python scripts/train_isolation_forest.py
  python scripts/train_isolation_forest.py --window 7d
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

PROCESSED_DIR = Path("data/processed")

# 20 cột số theo docs/feature_spec.md — tuyệt đối không gồm label_laundering
FEATURE_COLS: list[str] = [
    # A — Intensity
    "txn_count",
    "incoming_count",
    "outgoing_count",
    "active_days",
    "txn_per_active_day",
    # B — Money Flow
    "total_inflow",
    "total_outflow",
    "net_flow",
    "outflow_inflow_ratio",
    # C — Pass-through
    "rapid_outflow_ratio",
    "median_dwell_time",
    # D — Counterparty
    "unique_in_counterparties",
    "unique_out_counterparties",
    "new_counterparty_ratio",
    # E — Amount Distribution
    "median_amount",
    "p90_amount",
    "amount_std",
    "near_threshold_ratio",
    # F — Temporal Timing
    "off_hour_ratio",
    "median_inter_txn_gap",
]

META_COLS = {"account_key", "as_of_ts", "window", "label_laundering", "Is Laundering"}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train IsolationForest trên features_{split}_{window}.parquet")
    p.add_argument(
        "--window",
        default="7d",
        choices=("1d", "7d", "14d"),
        help="Cửa sổ đặc trưng (mặc định: 7d)",
    )
    return p.parse_args()


def _load_train_features(window: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"features_train_{window}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Khong tim thay {path}. Hay chay buoc extract features truoc."
        )
    df = pd.read_parquet(path)
    # Anti-leakage: drop moi cot nhan neu lo lot vao file
    drop_labels = [c for c in df.columns if c in META_COLS or "laundering" in c.lower()]
    # Giữ account_key chỉ để log; không đưa vào X
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Thieu {len(missing)} cot dac trung bat buoc: {missing}. "
            "Doi chieu docs/feature_spec.md."
        )
    return df


def _feature_matrix(df: pd.DataFrame) -> np.ndarray:
    X = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return X.to_numpy(dtype=np.float64)


def train(window: str) -> Path:
    print(f"[1/4] Doc features_train_{window}.parquet ...")
    df = _load_train_features(window)
    X = _feature_matrix(df)
    print(f"       n_samples={X.shape[0]:,}  n_features={X.shape[1]} (expect 20)")

    if X.shape[1] != 20:
        raise RuntimeError(f"Ky vong 20 cot so, nhan duoc {X.shape[1]}")

    print("[2/4] Fit IsolationForest(n_estimators=100, contamination=0.0005, ...)...")
    model = IsolationForest(
        n_estimators=100,
        contamination=0.0005,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    print("[3/4] Dao chieu decision_function + Min-Max -> [0, 1] (1=rui ro nhat)...")
    # sklearn: decision_function cao = binh thuong; dao dau de cao = bat thuong
    raw = model.decision_function(X)
    risk_raw = (-raw).reshape(-1, 1)
    scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    risk_01 = scaler.fit_transform(risk_raw).ravel()
    print(
        f"       risk_score min={risk_01.min():.4f}  max={risk_01.max():.4f}  "
        f"mean={risk_01.mean():.4f}"
    )

    out_path = PROCESSED_DIR / f"isolation_forest_model_{window}.joblib"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "scaler": scaler,
        "feature_cols": list(FEATURE_COLS),
        "window": window,
        "score_range": (0.0, 1.0),
        "score_meaning": "1.0 = highest risk, 0.0 = safest",
    }
    joblib.dump(artifact, out_path)
    print(f"[4/4] Da luu model + scaler -> {out_path}")
    return out_path


def main() -> None:
    args = _parse_args()
    train(args.window)


if __name__ == "__main__":
    main()
