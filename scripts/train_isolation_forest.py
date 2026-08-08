import os
import joblib
import pandas as pd
import numpy as np
import networkx as nx
from sklearn.ensemble import IsolationForest


def _feature_matrix(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    return df[feature_cols].fillna(0)


def _raw_to_ml_score(raw_scores: np.ndarray, min_s: float, max_s: float) -> np.ndarray:
    """Đảo Min-Max: decision_function càng âm → ml_score càng cao. Scale neo theo train."""
    if max_s - min_s == 0:
        return np.full(len(raw_scores), 50.0)
    scaled = ((max_s - raw_scores) / (max_s - min_s)) * 100
    return np.clip(scaled, 0, 100).round(2)


def _build_graph_scores(df_trans: pd.DataFrame) -> dict[str, float]:
    df_trans = df_trans.copy()
    df_trans["from_account_key"] = (
        df_trans["From Bank"].astype(str) + "_" + df_trans["Account"].astype(str)
    )
    df_trans["to_account_key"] = (
        df_trans["To Bank"].astype(str) + "_" + df_trans["Account.1"].astype(str)
    )

    G = nx.DiGraph()
    for _, row in df_trans.iterrows():
        u = row["from_account_key"]
        v = row["to_account_key"]
        w = float(row["Amount Paid"])
        if G.has_edge(u, v):
            G[u][v]["weight"] += w
        else:
            G.add_edge(u, v, weight=w)

    in_degrees = dict(G.in_degree())
    out_degrees = dict(G.out_degree())

    try:
        cycles = list(nx.simple_cycles(G))
        cycle_nodes = {node for cycle in cycles for node in cycle}
    except Exception:
        cycle_nodes = set()

    graph_scores: dict[str, float] = {}
    for acc in set(in_degrees) | set(out_degrees) | cycle_nodes:
        in_d = in_degrees.get(acc, 0)
        out_d = out_degrees.get(acc, 0)
        deg_score = min((in_d + out_d) * 15, 70)
        cycle_score = 30 if acc in cycle_nodes else 0
        graph_scores[acc] = min(deg_score + cycle_score, 100)
    return graph_scores


def _rule_score_row(row: pd.Series) -> float:
    r_score = 0
    if row["vol_30d"] > 30000:
        r_score += 40
    if row["near_threshold_ratio"] > 0:
        r_score += 30
    if row["off_hour_ratio"] > 0.3:
        r_score += 30
    return min(r_score, 100)


def _score_split(
    df_feat: pd.DataFrame,
    model: IsolationForest,
    feature_cols: list[str],
    min_s: float,
    max_s: float,
    graph_scores: dict[str, float],
) -> pd.DataFrame:
    scored = df_feat.copy()
    X = _feature_matrix(scored, feature_cols)
    raw_scores = model.decision_function(X)
    scored["ml_score"] = _raw_to_ml_score(raw_scores, min_s, max_s)
    scored["graph_score"] = scored["account_key"].map(graph_scores).fillna(0).round(2)
    scored["rule_score"] = scored.apply(_rule_score_row, axis=1)
    scored["risk_score"] = (
        0.5 * scored["ml_score"] + 0.3 * scored["graph_score"] + 0.2 * scored["rule_score"]
    ).round(2)
    scored["is_anomaly"] = scored["risk_score"] > 60
    scored["typology_code"] = np.where(scored["is_anomaly"], "T01", "NONE")
    return scored


def train_and_score():
    output_dir = "data"
    train_path = os.path.join(output_dir, "features_train.csv")
    val_path = os.path.join(output_dir, "features_val.csv")
    test_path = os.path.join(output_dir, "features_test.csv")

    scored_train_path = os.path.join(output_dir, "scored_train.csv")
    scored_val_path = os.path.join(output_dir, "scored_val.csv")
    scored_test_path = os.path.join(output_dir, "scored_test.csv")
    model_output_path = os.path.join(output_dir, "isolation_forest_model.joblib")

    trans_path = "HI-Sample_Trans.csv"
    if not os.path.exists(trans_path):
        trans_path = "tests/fixtures/aml/HI-Sample_Trans.csv"

    print("⏳ 1. Đang đọc features_train / val / test và file giao dịch...")
    for path in (train_path, val_path, test_path):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"❌ Không tìm thấy file {path}. Hãy chạy scripts/extract_features.py trước!"
            )
    if not os.path.exists(trans_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file giao dịch {trans_path}.")

    df_train = pd.read_csv(train_path)
    df_val = pd.read_csv(val_path)
    df_test = pd.read_csv(test_path)
    df_trans = pd.read_csv(trans_path)

    # -------------------------------------------------------------
    # NHÁNH 1: ML ENGINE — fit CHỈ trên train
    # -------------------------------------------------------------
    print("⏳ 2. [Nhánh 1] Fit Isolation Forest trên data/features_train.csv...")
    feature_cols = [c for c in df_train.columns if c != "account_key"]
    X_train = _feature_matrix(df_train, feature_cols)

    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X_train)

    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(model, model_output_path)
    print(f"💾 Đã lưu model: {model_output_path}")

    # Scale ml_score neo theo phân phối train (tránh leakage từ val/test)
    train_raw = model.decision_function(X_train)
    min_s, max_s = float(train_raw.min()), float(train_raw.max())

    # -------------------------------------------------------------
    # NHÁNH 2: GRAPH ENGINE (NetworkX) — dựng 1 lần từ toàn bộ TX
    # -------------------------------------------------------------
    print("⏳ 3. [Nhánh 2] Dựng đồ thị tài khoản NetworkX & Phân tích cấu trúc...")
    graph_scores = _build_graph_scores(df_trans)

    # -------------------------------------------------------------
    # Score cả 3 tập: ML (model đã fit) + Graph + Rule → risk_score
    # -------------------------------------------------------------
    print("⏳ 4. Chấm điểm Train / Val / Test (ML + Graph + Rule Fusion)...")
    scored_train = _score_split(df_train, model, feature_cols, min_s, max_s, graph_scores)
    scored_val = _score_split(df_val, model, feature_cols, min_s, max_s, graph_scores)
    scored_test = _score_split(df_test, model, feature_cols, min_s, max_s, graph_scores)

    scored_train.to_csv(scored_train_path, index=False)
    scored_val.to_csv(scored_val_path, index=False)
    scored_test.to_csv(scored_test_path, index=False)

    print("🎉 BƯỚC 2 HOÀN THÀNH!")
    print(
        f"🔥 High-risk (>60): train={scored_train['is_anomaly'].sum()}, "
        f"val={scored_val['is_anomaly'].sum()}, test={scored_test['is_anomaly'].sum()}"
    )
    print(f"📁 {scored_train_path}")
    print(f"📁 {scored_val_path}")
    print(f"📁 {scored_test_path}")
    print(f"💾 {model_output_path}")


if __name__ == "__main__":
    train_and_score()
