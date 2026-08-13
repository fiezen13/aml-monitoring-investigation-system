"""Chấm anomaly_score + top_anomalous_features cho snapshot 7d.

Ví dụ:
  python scripts/generate_scores.py
  python scripts/generate_scores.py --window 7d
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROCESSED_DIR = Path("data/processed")
MODEL_VERSION = "if_baseline_7d_v1"
SPLITS = ("train", "val", "test")

# Fallback nếu artifact cũ không có feature_cols
DEFAULT_FEATURE_COLS = [
    "txn_count",
    "incoming_count",
    "outgoing_count",
    "active_days",
    "txn_per_active_day",
    "total_inflow",
    "total_outflow",
    "net_flow",
    "outflow_inflow_ratio",
    "rapid_outflow_ratio",
    "median_dwell_time",
    "unique_in_counterparties",
    "unique_out_counterparties",
    "new_counterparty_ratio",
    "median_amount",
    "p90_amount",
    "amount_std",
    "repeated_amount_ratio",
    "median_inter_txn_gap",
    "p10_inter_txn_gap",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate IF scores + anomalous feature explanations")
    p.add_argument("--window", default="7d", choices=("1d", "7d", "14d"))
    p.add_argument(
        "--model",
        default=None,
        help="Duong dan joblib (mac dinh: isolation_forest_model_{window}.joblib)",
    )
    p.add_argument(
        "--output",
        default=str(PROCESSED_DIR / "if_scores_v1.parquet"),
    )
    p.add_argument("--processed-dir", default=str(PROCESSED_DIR), help="Thu muc feature artifacts")
    return p.parse_args()


def _load_artifact(path: Path) -> dict:
    art = joblib.load(path)
    if not isinstance(art, dict) or "model" not in art or "scaler" not in art:
        raise ValueError(f"Artifact khong hop le (can model+scaler): {path}")
    if "feature_cols" not in art:
        art["feature_cols"] = list(DEFAULT_FEATURE_COLS)
    return art


def _load_features(
    window: str,
    splits: tuple[str, ...] = SPLITS,
    processed_dir: Path = PROCESSED_DIR,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for split in splits:
        path = processed_dir / f"features_{split}_{window}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Thieu {path}")
        df = pd.read_parquet(path)
        df["split"] = split
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _train_percentiles(
    train: pd.DataFrame, feature_cols: list[str]
) -> tuple[pd.Series, pd.Series, dict[str, np.ndarray]]:
    """p5/p95 + mang sorted de tinh percentile rank (chi fit tren TRAIN)."""
    feat_df = train[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    p5 = feat_df.quantile(0.05)
    p95 = feat_df.quantile(0.95)
    sorted_cols = {c: np.sort(feat_df[c].to_numpy(dtype=np.float64)) for c in feature_cols}
    return p5, p95, sorted_cols


def _anomaly_scores(model, scaler, feature_matrix: np.ndarray) -> np.ndarray:
    raw = model.decision_function(feature_matrix)
    risk_raw = (-raw).reshape(-1, 1)
    scores = scaler.transform(risk_raw).ravel()
    return np.clip(scores, 0.0, 1.0)


def _build_top_anomalous_features(
    feature_matrix: np.ndarray,
    feature_cols: list[str],
    p5: pd.Series,
    p95: pd.Series,
    sorted_cols: dict[str, np.ndarray],
) -> list[str]:
    """Numpy vectorized: moi hang -> JSON list cac feature <p5 hoac >p95."""
    n_rows = feature_matrix.shape[0]
    lo = p5[feature_cols].to_numpy(dtype=np.float64)
    hi = p95[feature_cols].to_numpy(dtype=np.float64)

    # percentile rank cho toan bo cot (searchsorted theo cot)
    pct = np.empty_like(feature_matrix)
    for j, col in enumerate(feature_cols):
        sorted_v = sorted_cols[col]
        idx = np.searchsorted(sorted_v, feature_matrix[:, j], side="right")
        pct[:, j] = 100.0 * idx / max(len(sorted_v), 1)

    mask = (feature_matrix < lo) | (feature_matrix > hi)
    out: list[str] = []
    for i in range(n_rows):
        cols_i = np.flatnonzero(mask[i])
        if cols_i.size == 0:
            out.append("[]")
            continue
        items = [
            {
                "feature": feature_cols[j],
                "value": round(float(feature_matrix[i, j]), 6),
                "percentile": int(round(float(pct[i, j]))),
            }
            for j in cols_i
        ]
        items.sort(key=lambda d: abs(d["percentile"] - 50), reverse=True)
        out.append(json.dumps(items, ensure_ascii=False))
    return out


def score_features(
    features: pd.DataFrame,
    artifact: dict,
    reference_train: pd.DataFrame,
) -> pd.DataFrame:
    """Score point-in-time features using a frozen train-only reference.

    `features` may contain an operational snapshot built from the complete
    history. Percentile explanations still use train only, so inference data
    cannot move its own reference distribution.
    """
    feature_cols: list[str] = list(artifact["feature_cols"])
    missing = [column for column in feature_cols if column not in features.columns]
    if missing:
        raise ValueError(f"Thieu cot feature: {missing}")
    reference_missing = [column for column in feature_cols if column not in reference_train.columns]
    if reference_missing:
        raise ValueError(f"Train reference thieu cot feature: {reference_missing}")

    scored = features.copy()
    reference = reference_train.copy()
    for column in feature_cols:
        scored[column] = pd.to_numeric(scored[column], errors="coerce").fillna(0.0)
        reference[column] = pd.to_numeric(reference[column], errors="coerce").fillna(0.0)

    p5, p95, sorted_cols = _train_percentiles(reference, feature_cols)
    feature_matrix = scored[feature_cols].to_numpy(dtype=np.float64)
    scored["anomaly_score"] = _anomaly_scores(artifact["model"], artifact["scaler"], feature_matrix)
    scored["model_version"] = str(artifact.get("model_version") or MODEL_VERSION)
    scored["top_anomalous_features"] = _build_top_anomalous_features(
        feature_matrix,
        feature_cols,
        p5,
        p95,
        sorted_cols,
    )
    return scored[
        [
            "account_key",
            "as_of_ts",
            "window",
            *feature_cols,
            "anomaly_score",
            "model_version",
            "top_anomalous_features",
        ]
    ].copy()


def generate_scores(
    window: str,
    model_path: Path,
    output_path: Path,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    print(f"[1/5] Load model {model_path} ...")
    art = _load_artifact(model_path)
    feature_cols: list[str] = list(art["feature_cols"])
    if len(feature_cols) != 20:
        raise RuntimeError(f"Ky vong 20 feature, artifact co {len(feature_cols)}")

    print(f"[2/5] Load features_*_{window}.parquet (train/val/test) ...")
    df = _load_features(window, processed_dir=processed_dir)
    train = df[df["split"] == "train"]
    if train.empty:
        raise RuntimeError("Khong co hang split=train de tinh p5/p95.")

    print("[3/5] Tinh p5/p95 tren TRAIN (dong bang cho val/test) ...")
    p5, p95, _ = _train_percentiles(train, feature_cols)
    print(
        "       Vi du repeated_amount_ratio: "
        f"p5={p5['repeated_amount_ratio']:.6f} p95={p95['repeated_amount_ratio']:.6f}"
    )

    print("[4/5] Cham anomaly_score [0,1] + top_anomalous_features ...")
    out = score_features(df, art, train)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(
        f"[5/5] -> {output_path} | rows={len(out):,} | "
        f"score mean={out['anomaly_score'].mean():.4f} "
        f"p99={out['anomaly_score'].quantile(0.99):.4f}"
    )
    return output_path


def main() -> None:
    args = _parse_args()
    window = args.window
    processed_dir = Path(args.processed_dir)
    model_path = Path(args.model) if args.model else processed_dir / f"isolation_forest_model_{window}.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Khong tim thay model: {model_path}")
    generate_scores(window, model_path, Path(args.output), processed_dir)


if __name__ == "__main__":
    main()
