import os
import pandas as pd
import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, classification_report


def evaluate_model():
    scored_path = "data/scored_alerts.csv"
    if not os.path.exists(scored_path):
        scored_path = "scored_alerts.csv"

    trans_path = "HI-Sample_Trans.csv"
    if not os.path.exists(trans_path):
        trans_path = "tests/fixtures/aml/HI-Sample_Trans.csv"

    print(f"⏳ 1. Đang đọc kết quả chấm điểm từ: {scored_path}...")
    if not os.path.exists(scored_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file {scored_path}. Hãy chạy Bước 2 trước!")

    df_scored = pd.read_csv(scored_path)
    df_trans = pd.read_csv(trans_path)

    print("⏳ 2. Ánh xạ nhãn Ground Truth (Is Laundering) từ file giao dịch gốc...")
    # Chuẩn hóa nhãn rửa tiền về dạng số
    df_trans['Is Laundering'] = pd.to_numeric(df_trans['Is Laundering'], errors='coerce').fillna(0).astype(int)

    df_trans['from_account_key'] = df_trans['From Bank'].astype(str) + "_" + df_trans['Account'].astype(str)
    df_trans['to_account_key'] = df_trans['To Bank'].astype(str) + "_" + df_trans['Account.1'].astype(str)

    # Một tài khoản bị coi là rửa tiền nếu phát sinh giao dịch rửa tiền (nhãn 1)
    acc_laundering_from = df_trans.groupby('from_account_key')['Is Laundering'].max().to_dict()
    acc_laundering_to = df_trans.groupby('to_account_key')['Is Laundering'].max().to_dict()

    all_acc_laundering = {}
    for acc in set(list(acc_laundering_from.keys()) + list(acc_laundering_to.keys())):
        all_acc_laundering[acc] = max(acc_laundering_from.get(acc, 0), acc_laundering_to.get(acc, 0))

    df_scored['y_true'] = df_scored['account_key'].map(all_acc_laundering).fillna(0).astype(int)
    
    # Dự đoán rủi ro dựa trên cờ ngắt ngưỡng risk_score > 60
    df_scored['y_pred'] = (df_scored['risk_score'] > 60).astype(int)

    print("⏳ 3. Tính toán các chỉ số đánh giá Acceptance Criteria...")
    precision = precision_score(df_scored['y_true'], df_scored['y_pred'], zero_division=0)
    recall = recall_score(df_scored['y_true'], df_scored['y_pred'], zero_division=0)
    f1 = f1_score(df_scored['y_true'], df_scored['y_pred'], zero_division=0)
    roc_auc = roc_auc_score(df_scored['y_true'], df_scored['risk_score'])

    print("\n=======================================================")
    print("📊 BÁO CÁO NGHIỆM THU HIỆU NĂNG MÔ HÌNH (EVALUATION REPORT)")
    print("=======================================================")
    print(f"🔹 Tổng số tài khoản đánh giá: {len(df_scored)}")
    print(f"🔹 Số tài khoản rửa tiền thật (Ground Truth = 1): {df_scored['y_true'].sum()}")
    print(f"🔹 Số tài khoản dự đoán rủi ro cao (Alert Triggered): {df_scored['y_pred'].sum()}")
    print("-------------------------------------------------------")
    print(f"🎯 Precision (Độ chính xác): {precision:.4f} ({precision*100:.2f}%)")
    print(f"🎯 Recall (Độ phủ phát hiện): {recall:.4f} ({recall*100:.2f}%)")
    print(f"🎯 F1-Score:                  {f1:.4f}")
    print(f"🎯 ROC-AUC Score:            {roc_auc:.4f}")
    print("=======================================================")
    print("\n📋 Chi tiết phân loại (Classification Report):")
    print(classification_report(df_scored['y_true'], df_scored['y_pred'], target_names=['Bình thường (0)', 'Rửa tiền (1)']))


if __name__ == "__main__":
    evaluate_model()