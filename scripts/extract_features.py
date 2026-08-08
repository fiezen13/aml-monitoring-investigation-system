import os
import pandas as pd
import numpy as np


def _resolve_event_time(df: pd.DataFrame) -> pd.Series:
    """Ưu tiên occurred_at, fallback Timestamp (IBM AML)."""
    if "occurred_at" in df.columns:
        return pd.to_datetime(df["occurred_at"], errors="coerce")
    if "Timestamp" in df.columns:
        return pd.to_datetime(df["Timestamp"], errors="coerce")
    raise KeyError("Không tìm thấy cột thời gian 'occurred_at' hoặc 'Timestamp'.")


def _time_split(df: pd.DataFrame, time_col: str = "_split_time"):
    """Chia theo mốc thời gian: 60% train / 20% val / 20% test."""
    ordered = df.sort_values(by=time_col, kind="mergesort").reset_index(drop=True)
    n = len(ordered)
    train_end = int(n * 0.60)
    val_end = int(n * 0.80)
    train_df = ordered.iloc[:train_end].drop(columns=[time_col])
    val_df = ordered.iloc[train_end:val_end].drop(columns=[time_col])
    test_df = ordered.iloc[val_end:].drop(columns=[time_col])
    return train_df, val_df, test_df


def extract_features():
    # 1. Định nghĩa đường dẫn file đầu vào và đầu ra
    input_path = "HI-Sample_Trans.csv"
    if not os.path.exists(input_path):
        input_path = "tests/fixtures/aml/HI-Sample_Trans.csv"

    output_dir = "data"
    output_path = os.path.join(output_dir, "features_dataset.csv")
    train_path = os.path.join(output_dir, "features_train.csv")
    val_path = os.path.join(output_dir, "features_val.csv")
    test_path = os.path.join(output_dir, "features_test.csv")

    print(f"⏳ 1. Đang đọc dữ liệu giao dịch mẫu từ: {input_path}...")
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"❌ Không tìm thấy file {input_path}. Hãy kiểm tra lại đường dẫn trong repo!"
        )

    df = pd.read_csv(input_path)
    # Chuẩn hóa cột thời gian rồi sắp xếp giao dịch theo mốc thời gian
    df["dt"] = _resolve_event_time(df)
    df["dt"] = df["dt"].ffill().bfill()
    df = df.sort_values(by="dt", kind="mergesort").reset_index(drop=True)

    print("⏳ 2. Chuẩn hóa khóa tài khoản (account_key)...")
    df["from_account_key"] = df["From Bank"].astype(str) + "_" + df["Account"].astype(str)
    df["to_account_key"] = df["To Bank"].astype(str) + "_" + df["Account.1"].astype(str)
    df["amount"] = df["Amount Paid"].astype(float)

    # Tính các cờ chỉ số giao dịch đơn lẻ
    df["is_interbank"] = (df["From Bank"].astype(str) != df["To Bank"].astype(str)).astype(int)
    df["is_off_hour"] = df["dt"].dt.hour.isin([0, 1, 2, 3, 4, 5]).astype(int)
    df["is_near_threshold"] = ((df["amount"] >= 9000) & (df["amount"] < 10000)).astype(int)

    print("⏳ 3. Tách luồng tiền Ra (Outgoing) và Tiền Vào (Incoming)...")
    # Luồng tiền VÀO (Incoming)
    df_in = df[
        ["dt", "to_account_key", "amount", "from_account_key", "is_interbank", "is_off_hour", "is_near_threshold"]
    ].copy()
    df_in.columns = [
        "dt",
        "account_key",
        "amount_in",
        "counterparty",
        "is_interbank",
        "is_off_hour",
        "is_near_threshold",
    ]
    df_in["direction"] = "IN"
    df_in["amount_out"] = 0.0

    # Luồng tiền RA (Outgoing)
    df_out = df[
        ["dt", "from_account_key", "amount", "to_account_key", "is_interbank", "is_off_hour", "is_near_threshold"]
    ].copy()
    df_out.columns = [
        "dt",
        "account_key",
        "amount_out",
        "counterparty",
        "is_interbank",
        "is_off_hour",
        "is_near_threshold",
    ]
    df_out["direction"] = "OUT"
    df_out["amount_in"] = 0.0

    df_all = pd.concat([df_in, df_out], ignore_index=True)
    df_all["amount_total"] = df_all["amount_in"] + df_all["amount_out"]

    print("⏳ 4. Tính toán Rolling Window (1d, 7d, 30d) & đặc trưng nâng cao...")
    max_dt = df_all["dt"].max()
    dt_1d = max_dt - pd.Timedelta(days=1)
    dt_7d = max_dt - pd.Timedelta(days=7)
    dt_30d = max_dt - pd.Timedelta(days=30)

    records = []
    grouped = df_all.groupby("account_key")

    for acc_key, group in grouped:
        # Rolling window features
        g_1d = group[group["dt"] >= dt_1d]
        g_7d = group[group["dt"] >= dt_7d]
        g_30d = group[group["dt"] >= dt_30d]

        vol_1d = g_1d["amount_total"].sum()
        vol_7d = g_7d["amount_total"].sum()
        vol_30d = g_30d["amount_total"].sum()

        tx_cnt_1d = len(g_1d)
        tx_cnt_7d = len(g_7d)
        tx_cnt_30d = len(g_30d)

        # Thống kê phân bố số tiền
        amounts = group["amount_total"]
        amount_median = amounts.median()
        amount_std = amounts.std(ddof=0) if len(amounts) > 1 else 0.0

        near_threshold_ratio = group["is_near_threshold"].mean()
        off_hour_ratio = group["is_off_hour"].mean()
        interbank_ratio = group["is_interbank"].mean()

        # Số dư còn lại (Net balance)
        total_in = group["amount_in"].sum()
        total_out = group["amount_out"].sum()
        end_balance = total_in - total_out

        # Tỷ lệ đối tác mới
        cps = group["counterparty"].unique()
        cp_counts = group["counterparty"].value_counts()
        new_cps_count = (cp_counts == 1).sum()
        new_counterparties_ratio = new_cps_count / len(cps) if len(cps) > 0 else 0.0

        # Thời gian lưu tiền trung vị (Holding time in minutes)
        in_times = group[group["direction"] == "IN"]["dt"].sort_values()
        out_times = group[group["direction"] == "OUT"]["dt"].sort_values()

        holding_times = []
        for t_in in in_times:
            future_outs = out_times[out_times >= t_in]
            if not future_outs.empty:
                diff_minutes = (future_outs.iloc[0] - t_in).total_seconds() / 60.0
                holding_times.append(diff_minutes)

        holding_time_median = np.median(holding_times) if len(holding_times) > 0 else 0.0

        records.append(
            {
                "account_key": acc_key,
                "vol_1d": round(vol_1d, 2),
                "vol_7d": round(vol_7d, 2),
                "vol_30d": round(vol_30d, 2),
                "tx_cnt_1d": int(tx_cnt_1d),
                "tx_cnt_7d": int(tx_cnt_7d),
                "tx_cnt_30d": int(tx_cnt_30d),
                "amount_median": round(amount_median, 2),
                "amount_std": round(amount_std, 2),
                "near_threshold_ratio": round(near_threshold_ratio, 4),
                "holding_time_median": round(holding_time_median, 2),
                "end_balance": round(end_balance, 2),
                "new_counterparties_ratio": round(new_counterparties_ratio, 4),
                "off_hour_ratio": round(off_hour_ratio, 4),
                "interbank_ratio": round(interbank_ratio, 4),
                # Mốc thời gian để chia train/val/test (last activity của account)
                "_split_time": group["dt"].max(),
            }
        )

    final_df = pd.DataFrame(records)

    print("⏳ 5. Chia dataset theo mốc thời gian (60% train / 20% val / 20% test)...")
    train_df, val_df, test_df = _time_split(final_df, time_col="_split_time")
    full_df = final_df.drop(columns=["_split_time"])

    # Tạo thư mục data/ và xuất file CSV
    os.makedirs(output_dir, exist_ok=True)
    full_df.to_csv(output_path, index=False)
    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print(
        f"🎉 BƯỚC 1 HOÀN THÀNH! Đã trích xuất đặc trưng cho {len(full_df)} tài khoản "
        f"(train={len(train_df)}, val={len(val_df)}, test={len(test_df)})."
    )
    print(f"📁 Full:  {output_path}")
    print(f"📁 Train: {train_path}")
    print(f"📁 Val:   {val_path}")
    print(f"📁 Test:  {test_path}")


if __name__ == "__main__":
    extract_features()
