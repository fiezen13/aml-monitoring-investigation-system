"""Fit IsolationForest trên train; score Train/Val/Test + Graph (NetworkX) + Rules."""

from __future__ import annotations

from pathlib import Path

import joblib
import networkx as nx
import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import IsolationForest

PROCESSED_DIR = Path("data/processed")
MODEL_PATH = Path("data/isolation_forest_model.joblib")
SPLITS = ("train", "val", "test")


def _feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c != "account_key"]


def _raw_to_ml_score(raw: np.ndarray, min_s: float, max_s: float) -> np.ndarray:
    if max_s - min_s == 0:
        return np.full(len(raw), 50.0)
    scaled = ((max_s - raw) / (max_s - min_s)) * 100.0
    return np.clip(scaled, 0.0, 100.0)


def _graph_scores_from_tx(tx_path: Path) -> dict[str, float]:
    """Degree + cycle proxy (SCC size>1 / self-loop) — vectorized edge agg, không iter từng TX."""
    print(f"   Graph: aggregate edges từ {tx_path.name}...")
    edges = (
        pl.read_parquet(tx_path)
        .group_by(["from_account_key", "to_account_key"])
        .agg(pl.col("amount").sum().alias("weight"))
    )
    src = edges["from_account_key"].to_list()
    dst = edges["to_account_key"].to_list()
    w = edges["weight"].to_list()

    G = nx.DiGraph()
    G.add_weighted_edges_from(zip(src, dst, w))

    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # simple_cycles không khả thi ở quy mô lớn → SCC (>1) + self-loop ≡ thuộc chu trình
    cycle_nodes: set[str] = set()
    for scc in nx.strongly_connected_components(G):
        if len(scc) > 1:
            cycle_nodes.update(scc)
    cycle_nodes.update(n for n in G.nodes if G.has_edge(n, n))

    scores: dict[str, float] = {}
    for acc in set(in_deg) | set(out_deg):
        deg_score = min((in_deg.get(acc, 0) + out_deg.get(acc, 0)) * 15, 70)
        cycle_score = 30 if acc in cycle_nodes else 0
        scores[acc] = float(min(deg_score + cycle_score, 100))
    print(f"   Graph: nodes={G.number_of_nodes():,} edges={G.number_of_edges():,} cycle_nodes={len(cycle_nodes):,}")
    return scores


def _rule_scores(df: pd.DataFrame) -> np.ndarray:
    """Vectorized rule engine."""
    r = np.zeros(len(df), dtype=np.float64)
    r += np.where(df["vol_30d"].to_numpy() > 30000, 40.0, 0.0)
    r += np.where(df["near_threshold_ratio"].to_numpy() > 0, 30.0, 0.0)
    r += np.where(df["off_hour_ratio"].to_numpy() > 0.3, 30.0, 0.0)
    return np.minimum(r, 100.0)


def _score_split(
    df: pd.DataFrame,
    model: IsolationForest,
    feature_cols: list[str],
    min_s: float,
    max_s: float,
    graph_scores: dict[str, float],
) -> pd.DataFrame:
    X = df[feature_cols].fillna(0.0).to_numpy(dtype=np.float64)
    raw = model.decision_function(X)
    out = df.copy()
    out["ml_score"] = np.round(_raw_to_ml_score(raw, min_s, max_s), 2)
    out["graph_score"] = out["account_key"].map(graph_scores).fillna(0.0).astype(float).round(2)
    out["rule_score"] = np.round(_rule_scores(out), 2)
    out["risk_score"] = (
        0.5 * out["ml_score"] + 0.3 * out["graph_score"] + 0.2 * out["rule_score"]
    ).round(2)
    return out


def train_and_score() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    train_feat_path = PROCESSED_DIR / "features_train.csv"
    if not train_feat_path.exists():
        raise FileNotFoundError(
            f"❌ Không tìm thấy {train_feat_path}. Chạy extract_features.py trước!"
        )

    print("⏳ 1. Đọc features_train và fit IsolationForest...")
    df_train = pd.read_csv(train_feat_path)
    feature_cols = _feature_cols(df_train)
    X_train = df_train[feature_cols].fillna(0.0).to_numpy(dtype=np.float64)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.0005,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"💾 Model → {MODEL_PATH}")

    train_raw = model.decision_function(X_train)
    min_s, max_s = float(train_raw.min()), float(train_raw.max())

    for split in SPLITS:
        feat_path = PROCESSED_DIR / f"features_{split}.csv"
        tx_path = PROCESSED_DIR / f"transactions_{split}.parquet"
        print(f"⏳ 2. Score [{split}] — ML + Graph + Rules...")
        df = pd.read_csv(feat_path)
        graph_scores = _graph_scores_from_tx(tx_path)
        scored = _score_split(df, model, feature_cols, min_s, max_s, graph_scores)
        out = PROCESSED_DIR / f"scored_{split}.csv"
        scored.to_csv(out, index=False)
        print(
            f"   ✅ {out} | n={len(scored):,} | "
            f"risk>60={int((scored['risk_score'] > 60).sum()):,} | "
            f"mean_risk={scored['risk_score'].mean():.2f}"
        )

    print("🎉 TRAIN + SCORE FUSION XONG")


if __name__ == "__main__":
    train_and_score()
