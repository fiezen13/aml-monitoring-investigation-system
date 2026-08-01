import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def train_and_score():
    input_path = "data/features_dataset.csv"  # Hoặc data/features_dataset.csv tùy vị trí bạn lưu
    model_output_path = "data/isolation_forest_model.joblib"
    output_path = "data/scored_alerts.csv"

    print("⏳ 1. Đang đọc file đặc trưng tài khoản...")
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"❌ Không tìm thấy file {input_path}. Hãy chạy Step 1 trước!"
        )

    df = pd.read_csv(input_path)

    print("⏳ 2. Chuẩn bị ma trận đặc trưng cho Isolation Forest...")
    # CHÚ Ý QUAN TRỌNG (Nguyên tắc ND1): Cấm tuyệt đối đưa cột nhãn rửa tiền vào đây.
    # Chỉ chọn các cột số học đặc trưng hành vi:
    feature_cols = [
        "total_volume_30d",
        "tx_count_30d",
        "in_out_ratio",
        "unique_counterparties",
        "max_amount",
    ]

    # Điền giá trị NaN bằng 0 để tránh lỗi mô hình
    X = df[feature_cols].fillna(0)

    print("⏳ 3. Huấn luyện mô hình Isolation Forest...")
    # contamination=0.05 nghĩa là giả định khoảng 5% dữ liệu có thể là bất thường (anomalies)
    model = IsolationForest(
        n_estimators=100, contamination=0.05, random_state=42
    )
    model.fit(X)

    print("⏳ 4. Tính toán điểm bất thường và quy đổi Risk Score (0 - 100)...")
    # decision_function trả về điểm: số càng âm càng bất thường (càng rủi ro cao)
    raw_scores = model.decision_function(X)
    df["anomaly_score"] = raw_scores

    # Dùng Min-Max Scaling để quy đổi điểm thô ra thang điểm [0 - 100] phục vụ UI ProgressBar
    min_s, max_s = raw_scores.min(), raw_scores.max()
    if max_s - min_s == 0:
        df["risk_score"] = 50.0  # Tránh lỗi chia cho 0 nếu data quá ít
    else:
        # Đảo ngược công thức vì điểm thô càng nhỏ (âm nhiều) thì rủi ro càng cao
        df["risk_score"] = (
            ((max_s - raw_scores) / (max_s - min_s)) * 100
        ).round(2)

    # Đặt cờ ngắt ngưỡng rủi ro cao: risk_score > 70 (Mock threshold theo tài liệu)
    df["is_anomaly"] = df["risk_score"] > 70

    # Gán mã typology nghi vấn giả định cho bản Demo MVP (Ví dụ T01 hoặc T05)
    df.loc[df["is_anomaly"] == True, "typology_code"] = "T01"
    df.loc[df["is_anomaly"] == False, "typology_code"] = "NONE"

    print("⏳ 5. Xuất kết quả file scored_alerts.csv và lưu model...")
    os.makedirs("data", exist_ok=True)
    df.to_csv(output_path, index=False)
    joblib.dump(model, model_output_path)

    high_risk_count = df["is_anomaly"].sum()
    print(
        f"🎉 THÀNH CÔNG! Đã chấm điểm rủi ro cho {len(df)} tài khoản. Phát hiện {high_risk_count} tài khoản rủi ro cao (>70)."
    )
    print(f"📁 File cảnh báo lưu tại: {output_path}")
    print(f"💾 File Model lưu tại: {model_output_path}")


if __name__ == "__main__":
    train_and_score()