import os
import joblib
import pandas as pd
import numpy as np
import networkx as nx
from sklearn.ensemble import IsolationForest


def train_and_score():
    features_path = "data/features_dataset.csv"
    if not os.path.exists(features_path):
        features_path = "features_dataset.csv"

    trans_path = "HI-Sample_Trans.csv"
    if not os.path.exists(trans_path):
        trans_path = "tests/fixtures/aml/HI-Sample_Trans.csv"

    output_dir = "data"
    output_scored_path = os.path.join(output_dir, "scored_alerts.csv")
    model_output_path = os.path.join(output_dir, "isolation_forest_model.joblib")

    print("⏳ 1. Đang đọc tập đặc trưng và file giao dịch...")
    if not os.path.exists(features_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file {features_path}. Hãy chạy Bước 1 trước!")

    df_feat = pd.read_csv(features_path)
    df_trans = pd.read_csv(trans_path)

    # -------------------------------------------------------------
    # NHÁNH 1: ML ENGINE (Isolation Forest)
    # -------------------------------------------------------------
    print("⏳ 2. [Nhánh 1] Huấn luyện Isolation Forest trên 14 đặc trưng...")
    # Nguyên tắc ND1: Không đưa cột nhãn rửa tiền vào danh sách đặc trưng
    feature_cols = [c for c in df_feat.columns if c != 'account_key']
    X = df_feat[feature_cols].fillna(0)

    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)

    raw_scores = model.decision_function(X)
    min_s, max_s = raw_scores.min(), raw_scores.max()
    if max_s - min_s == 0:
        ml_scores = np.full(len(raw_scores), 50.0)
    else:
        # Đảo ngược Min-Max Scaling (điểm thô càng âm -> rủi ro càng cao)
        ml_scores = (((max_s - raw_scores) / (max_s - min_s)) * 100).round(2)
    
    df_feat['ml_score'] = ml_scores

    # -------------------------------------------------------------
    # NHÁNH 2: GRAPH ENGINE (NetworkX)
    # -------------------------------------------------------------
    print("⏳ 3. [Nhánh 2] Dựng đồ thị tài khoản NetworkX & Phân tích cấu trúc...")
    df_trans['from_account_key'] = df_trans['From Bank'].astype(str) + "_" + df_trans['Account'].astype(str)
    df_trans['to_account_key'] = df_trans['To Bank'].astype(str) + "_" + df_trans['Account.1'].astype(str)

    G = nx.DiGraph()
    for _, row in df_trans.iterrows():
        u = row['from_account_key']
        v = row['to_account_key']
        w = float(row['Amount Paid'])
        if G.has_edge(u, v):
            G[u][v]['weight'] += w
        else:
            G.add_edge(u, v, weight=w)

    in_degrees = dict(G.in_degree())
    out_degrees = dict(G.out_degree())

    # Phát hiện nút thuộc chu trình (Simple Cycles)
    try:
        cycles = list(nx.simple_cycles(G))
        cycle_nodes = set([node for cycle in cycles for node in cycle])
    except Exception:
        cycle_nodes = set()

    graph_scores = {}
    for acc in df_feat['account_key']:
        in_d = in_degrees.get(acc, 0)
        out_d = out_degrees.get(acc, 0)
        
        # Điểm liên kết mạng lưới (Degree score) + Điểm giao dịch vòng (Cycle score)
        deg_score = min((in_d + out_d) * 15, 70)
        cycle_score = 30 if acc in cycle_nodes else 0
        graph_scores[acc] = min(deg_score + cycle_score, 100)

    df_feat['graph_score'] = df_feat['account_key'].map(graph_scores).fillna(0).round(2)

    # -------------------------------------------------------------
    # NHÁNH 3: RULE ENGINE
    # -------------------------------------------------------------
    print("⏳ 4. [Nhánh 3] Đánh giá bộ luật kịch bản AML (T01, T05, CTR)...")
    rule_scores = []
    for _, row in df_feat.iterrows():
        r_score = 0
        if row['vol_30d'] > 30000:
            r_score += 40
        if row['near_threshold_ratio'] > 0:
            r_score += 30
        if row['off_hour_ratio'] > 0.3:
            r_score += 30
        rule_scores.append(min(r_score, 100))

    df_feat['rule_score'] = rule_scores

    # -------------------------------------------------------------
    # HỢP NHẤT ĐIỂM RỦI RO (RISK FUSION)
    # -------------------------------------------------------------
    print("⏳ 5. Hợp nhất điểm rủi ro 3 nhánh (Risk Fusion)...")
    df_feat['risk_score'] = (
        0.5 * df_feat['ml_score'] + 
        0.3 * df_feat['graph_score'] + 
        0.2 * df_feat['rule_score']
    ).round(2)

    # Cờ ngắt ngưỡng rủi ro
    df_feat['is_anomaly'] = df_feat['risk_score'] > 60
    df_feat['typology_code'] = np.where(df_feat['is_anomaly'], 'T01', 'NONE')

    # Lưu kết quả file CSV và Model
    os.makedirs(output_dir, exist_ok=True)
    df_feat.to_csv(output_scored_path, index=False)
    joblib.dump(model, model_output_path)

    high_risk_cnt = df_feat['is_anomaly'].sum()
    print(f"🎉 BƯỚC 2 HOÀN THÀNH! Đã chấm điểm cho {len(df_feat)} tài khoản.")
    print(f"🔥 Phát hiện {high_risk_cnt} tài khoản rủi ro cao (> 60).")
    print(f"📁 Kết quả lưu tại: {output_scored_path}")
    print(f"💾 File Model lưu tại: {model_output_path}")


if __name__ == "__main__":
    train_and_score()