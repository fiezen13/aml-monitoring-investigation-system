import os
import pandas as pd
import numpy as np


def extract_features():
    # 1. Định nghĩa đường dẫn file đầu vào và đầu ra
    input_path = "tests/fixtures/aml/HI-Sample_Trans.csv"
    output_dir = "data"
    output_path = os.path.join(output_dir, "features_dataset.csv")

    print(f"⏳ 1. Đang đọc dữ liệu giao dịch mẫu từ: {input_path}...")
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"❌ Không tìm thấy file {input_path}. Hãy kiểm tra lại đường dẫn trong repo!"
        )

    # Đọc file CSV mẫu
    use_cols = [
        "Timestamp",
        "From Bank",
        "Account",
        "To Bank",
        "Account.1",
        "Amount Paid",
    ]
    df = pd.read_csv(input_path, usecols=use_cols)

    print("⏳ 2. Chuẩn hóa khóa tài khoản (account_key)...")
    # Bắt buộc ghép Bank + Account thành account_key duy nhất (Theo Mục 4.1 tài liệu Data Spec)
    df["from_account_key"] = (
        df["From Bank"].astype(str) + "_" + df["Account"].astype(str)
    )
    df["to_account_key"] = (
        df["To Bank"].astype(str) + "_" + df["Account.1"].astype(str)
    )
    df["amount"] = df["Amount Paid"].astype(float)

    print("⏳ 3. Tách luồng tiền Ra (Outgoing) và Tiền Vào (Incoming)...")
    # Luồng tiền RA
    df_out = df[["from_account_key", "amount", "to_account_key"]].copy()
    df_out.columns = ["account_key", "amount_out", "counterparty"]

    # Luồng tiền VÀO
    df_in = df[["to_account_key", "amount", "from_account_key"]].copy()
    df_in.columns = ["account_key", "amount_in", "counterparty"]

    print("⏳ 4. Gom nhóm (Aggregate) tính toán các chỉ số đặc trưng...")
    # SỬA LỖI: Dùng lambda x: set(x) cho cột counterparty để tạo tập hợp đối tác duy nhất
    agg_out = (
        df_out.groupby("account_key")
        .agg(
            total_out=("amount_out", "sum"),
            tx_count_out=("amount_out", "count"),
            max_amount_out=("amount_out", "max"),
            cps_out=("counterparty", lambda x: set(x)),
        )
        .reset_index()
    )

    agg_in = (
        df_in.groupby("account_key")
        .agg(
            total_in=("amount_in", "sum"),
            tx_count_in=("amount_in", "count"),
            max_amount_in=("amount_in", "max"),
            cps_in=("counterparty", lambda x: set(x)),
        )
        .reset_index()
    )

    print("⏳ 5. Hợp nhất hai luồng tiền và tính toán các New Key...")
    df_features = pd.merge(agg_out, agg_in, on="account_key", how="outer").fillna(
        {
            "total_out": 0,
            "tx_count_out": 0,
            "max_amount_out": 0,
            "total_in": 0,
            "tx_count_in": 0,
            "max_amount_in": 0,
        }
    )

    # Tính toán các chỉ số đặc trưng:
    # 1. total_volume_30d: Tổng tiền ra + Tổng tiền vào
    df_features["total_volume_30d"] = (
        df_features["total_out"] + df_features["total_in"]
    )

    # 2. tx_count_30d: Tổng số lượng giao dịch
    df_features["tx_count_30d"] = (
        df_features["tx_count_out"] + df_features["tx_count_in"]
    )

    # 3. max_amount: Giá trị giao dịch lớn nhất
    df_features["max_amount"] = df_features[
        ["max_amount_out", "max_amount_in"]
    ].max(axis=1)

    # 4. in_out_ratio: Tỷ lệ tiền ra / tiền vào (Tránh chia cho 0)
    df_features["in_out_ratio"] = (
        df_features["total_out"] / (df_features["total_in"] + 1e-5)
    ).round(4)

    # 5. unique_counterparties: Tổng số đối tác riêng biệt
    def count_unique_cps(row):
        out_set = (
            row["cps_out"] if isinstance(row["cps_out"], set) else set()
        )
        in_set = row["cps_in"] if isinstance(row["cps_in"], set) else set()
        return len(out_set.union(in_set))

    df_features["unique_counterparties"] = df_features.apply(
        count_unique_cps, axis=1
    )

    # Lọc lại đúng 6 cột Output tiêu chuẩn
    final_cols = [
        "account_key",
        "total_volume_30d",
        "tx_count_30d",
        "in_out_ratio",
        "unique_counterparties",
        "max_amount",
    ]
    final_df = df_features[final_cols]

    # Tạo thư mục data/ nếu chưa có
    os.makedirs(output_dir, exist_ok=True)

    # Xuất file CSV
    final_df.to_csv(output_path, index=False)
    print(
        f"🎉 THÀNH CÔNG! Đã trích xuất đặc trưng cho {len(final_df)} tài khoản."
    )
    print(f"📁 File đầu ra đã được lưu tại: {output_path}")


if __name__ == "__main__":
    extract_features()