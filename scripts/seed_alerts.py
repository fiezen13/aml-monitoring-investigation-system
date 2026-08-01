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
    csv_path = "scored_alerts.csv"
    if not os.path.exists(csv_path):
        csv_path = "data/scored_alerts.csv"

    print(f"⏳ 1. Đang đọc dữ liệu cảnh báo từ: {csv_path}...")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file {csv_path}. Hãy chạy Step 2 trước!")

    df = pd.read_csv(csv_path)

    # Lọc các tài khoản rủi ro cao (risk_score > 70)
    high_risk_df = df[df["risk_score"] > 70].copy()
    
    if high_risk_df.empty:
        print("⚠️ Không có tài khoản nào đạt ngưỡng > 70. Lấy top 10 tài khoản rủi ro nhất để demo...")
        high_risk_df = df.sort_values(by="risk_score", ascending=False).head(10).copy()

    print(f"🔍 Tìm thấy {len(high_risk_df)} tài khoản rủi ro cao cần lưu vào CSDL.")
    print(f"🔌 2. Kết nối CSDL PostgreSQL...")
    engine = create_engine(DB_URL)

    print("⏳ 3. Đang nạp dữ liệu khớp 100% Schema CSDL (customer -> account -> alert -> alert_reason)...")
    alerts_inserted = 0

    with engine.begin() as conn:
        for idx, row in high_risk_df.iterrows():
            raw_acc_key = str(row["account_key"])
            
            # Xử lý account_key chuẩn định dạng bank_code:account_number theo CHECK CONSTRAINT của DB
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

            # Step A: Ensure customer exists (thỏa mãn Foreign Key của account)
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

            # Step B: Ensure account exists (thỏa mãn Foreign Key của alert)
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

            # Step C: Insert into alert table (alert_id là TEXT Primary Key)
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
                    "detector": "ml",  # Khớp CHECK constraint (rule, ml, graph) trong DB
                    "risk_score": float(row["risk_score"]),
                    "status": "open"   # Khớp CHECK constraint (open, grouped, closed)
                }
            )

            # Step D: Insert into alert_reason table
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
                    "factor_code": "ML_ISOLATION_FOREST",
                    "factor_label": f"Phát hiện bất thường ML với điểm rủi ro {row['risk_score']}/100",
                    "contribution": float(row["risk_score"]),
                    "weight": 1.00
                }
            )
            alerts_inserted += 1

    print(f"🎉 THÀNH CÔNG RỰC RỠ! Đã nạp {alerts_inserted} cảnh báo khớp 100% CSDL PostgreSQL.")


if __name__ == "__main__":
    seed_alerts_to_db()