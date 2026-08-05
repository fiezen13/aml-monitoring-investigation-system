import os
import uuid
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load biến môi trường từ .env
load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/fin07"
)

def seed_alerts_to_db():
    csv_path = "data/scored_alerts.csv"
    if not os.path.exists(csv_path):
        csv_path = "scored_alerts.csv"

    print(f"⏳ 1. Đang đọc dữ liệu cảnh báo từ: {csv_path}...")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file {csv_path}. Hãy chạy Bước 2 trước!")

    df = pd.read_csv(csv_path)

    # 1. GOM ALERT THEO ACCOUNT_KEY: Lấy risk_score cao nhất cho mỗi tài khoản
    df_sorted = df.sort_values(by="risk_score", ascending=False)
    df_unique = df_sorted.drop_duplicates(subset=["account_key"]).copy()

    # Lọc các tài khoản rủi ro cao (risk_score > 60 hoặc lấy top 15)
    high_risk_df = df_unique[df_unique["risk_score"] > 60].copy()
    
    if high_risk_df.empty:
        print("⚠️ Không có tài khoản nào vượt ngưỡng 60. Lấy top 10 tài khoản rủi ro nhất để demo...")
        high_risk_df = df_unique.head(10).copy()

    print(f"🔍 Đã gom nhóm theo tài khoản. Tìm thấy {len(high_risk_df)} tài khoản rủi ro cao duy nhất.")
    print(f"🔌 2. Kết nối CSDL PostgreSQL...")
    engine = create_engine(DB_URL)

    print("⏳ 3. Đang nạp dữ liệu chuẩn CSDL & Explainable AI (3 Factors per Alert)...")
    alerts_inserted = 0

    with engine.begin() as conn:
        for idx, row in high_risk_df.iterrows():
            raw_acc_key = str(row["account_key"])
            
            # Xử lý account_key chuẩn định dạng bank_code:account_number theo CHECK CONSTRAINT
            if "_" in raw_acc_key:
                bank_code, acc_num = raw_acc_key.split("_", 1)
                formatted_acc_key = f"{bank_code}:{acc_num}"
            elif ":" in raw_acc_key:
                bank_code, acc_num = raw_acc_key.split(":", 1)
                formatted_acc_key = raw_acc_key
            else:
                bank_code, acc_num = "010", raw_acc_key
                formatted_acc_key = f"010:{raw_acc_key}"

            customer_id = f"CUST_{bank_code}_{acc_num}"

            # Step A: Ensure customer exists
            conn.execute(
                text("""
                    INSERT INTO customer (
                        customer_id, customer_type, prototype, occupation, 
                        declared_income_band, expected_monthly_volume, 
                        registered_country, onboarding_date, risk_rating
                    ) VALUES (
                        :customer_id, 'individual', 'salaried', 'Employee',
                        '10m_50m', 100000000.00, 'VN', '2024-01-01', 'medium'
                    ) ON CONFLICT (customer_id) DO NOTHING;
                """),
                {"customer_id": customer_id}
            )

            # Step B: Ensure account exists
            conn.execute(
                text("""
                    INSERT INTO account (
                        account_key, customer_id, bank_code, account_number, opened_at, status
                    ) VALUES (
                        :account_key, :customer_id, :bank_code, :account_number, '2024-01-01', 'active'
                    ) ON CONFLICT (account_key) DO NOTHING;
                """),
                {
                    "account_key": formatted_acc_key,
                    "customer_id": customer_id,
                    "bank_code": bank_code,
                    "account_number": acc_num
                }
            )

            # Step C: Insert into alert table
            alert_id = f"ALT_{uuid.uuid4().hex[:10].upper()}"
            typology = str(row["typology_code"]) if str(row["typology_code"]) != "NONE" else "T01"

            conn.execute(
                text("""
                    INSERT INTO alert (
                        alert_id, account_key, typology_code, detector, risk_score, status
                    ) VALUES (
                        :alert_id, :account_key, :typology_code, :detector, :risk_score, :status
                    ) ON CONFLICT (alert_id) DO NOTHING;
                """),
                {
                    "alert_id": alert_id,
                    "account_key": formatted_acc_key,
                    "typology_code": typology,
                    "detector": "ml",
                    "risk_score": float(row["risk_score"]),
                    "status": "open"
                }
            )

            # Step D: Insert 3 EXPLAINABLE FACTORS into alert_reason table (Thỏa mãn Nguyên tắc NT7)
            factors = [
                {
                    "factor_code": "ML_ISOLATION_FOREST",
                    "factor_label": f"Mô hình ML phát hiện bất thường hành vi (Điểm ML: {row['ml_score']}/100)",
                    "contribution": float(row["ml_score"]),
                    "weight": 0.50
                },
                {
                    "factor_code": "GRAPH_NETWORKX",
                    "factor_label": f"Đồ thị phát hiện liên kết rủi ro/chu trình (Điểm Graph: {row['graph_score']}/100)",
                    "contribution": float(row["graph_score"]),
                    "weight": 0.30
                },
                {
                    "factor_code": "RULE_ENGINE",
                    "factor_label": f"Vi phạm bộ luật kịch bản AML/ngưỡng CTR (Điểm Rule: {row['rule_score']}/100)",
                    "contribution": float(row["rule_score"]),
                    "weight": 0.20
                }
            ]

            for f in factors:
                conn.execute(
                    text("""
                        INSERT INTO alert_reason (
                            alert_id, factor_code, factor_label, contribution, weight
                        ) VALUES (
                            :alert_id, :factor_code, :factor_label, :contribution, :weight
                        ) ON CONFLICT (alert_id, factor_code) DO NOTHING;
                    """),
                    {
                        "alert_id": alert_id,
                        "factor_code": f["factor_code"],
                        "factor_label": f["factor_label"],
                        "contribution": f["contribution"],
                        "weight": f["weight"]
                    }
                )
            alerts_inserted += 1

    print(f"🎉 BƯỚC 3 HOÀN THÀNH! Đã nạp {alerts_inserted} cảnh báo duy nhất kèm 3 Explainable Factors vào PostgreSQL.")


if __name__ == "__main__":
    seed_alerts_to_db()