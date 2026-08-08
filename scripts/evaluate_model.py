import os
import pandas as pd
import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, classification_report


def _resolve_scored_path() -> str:
    """Ưu tiên test set; fallback scored_alerts.csv (pipeline cũ)."""
    candidates = (
        "data/scored_test.csv",
        "data/scored_alerts.csv",
        "scored_test.csv",
        "scored_alerts.csv",
    )
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "❌ Không tìm thấy data/scored_test.csv (hoặc scored_alerts.csv). "
        "Hãy chạy scripts/train_isolation_forest.py trước!"
    )


def _build_laundering_labels(df_trans: pd.DataFrame) -> dict:
    df_trans = df_trans.copy()
    df_trans["Is Laundering"] = (
        pd.to_numeric(df_trans["Is Laundering"], errors="coerce").fillna(0).astype(int)
    )
    df_trans["from_account_key"] = (
        df_trans["From Bank"].astype(str) + "_" + df_trans["Account"].astype(str)
    )
    df_trans["to_account_key"] = (
        df_trans["To Bank"].astype(str) + "_" + df_trans["Account.1"].astype(str)
    )
    acc_from = df_trans.groupby("from_account_key")["Is Laundering"].max().to_dict()
    acc_to = df_trans.groupby("to_account_key")["Is Laundering"].max().to_dict()
    all_acc = {}
    for acc in set(acc_from) | set(acc_to):
        all_acc[acc] = max(acc_from.get(acc, 0), acc_to.get(acc, 0))
    return all_acc


def _report_split(name: str, df_scored: pd.DataFrame, labels: dict) -> None:
    df = df_scored.copy()
    df["y_true"] = df["account_key"].map(labels).fillna(0).astype(int)
    df["y_pred"] = (df["risk_score"] > 60).astype(int)

    precision = precision_score(df["y_true"], df["y_pred"], zero_division=0)
    recall = recall_score(df["y_true"], df["y_pred"], zero_division=0)
    f1 = f1_score(df["y_true"], df["y_pred"], zero_division=0)
    # ROC-AUC cần cả 2 lớp; nếu split chỉ có 1 lớp thì bỏ qua
    if df["y_true"].nunique() < 2:
        roc_auc = float("nan")
        roc_auc_txt = "N/A (chỉ có 1 lớp nhãn)"
    else:
        roc_auc = roc_auc_score(df["y_true"], df["risk_score"])
        roc_auc_txt = f"{roc_auc:.4f}"

    print("\n=======================================================")
    print(f"📊 EVALUATION REPORT — {name}")
    print("=======================================================")
    print(f"🔹 Tổng số tài khoản đánh giá: {len(df)}")
    print(f"🔹 Số tài khoản rửa tiền thật (Ground Truth = 1): {df['y_true'].sum()}")
    print(f"🔹 Số tài khoản dự đoán rủi ro cao (Alert Triggered): {df['y_pred'].sum()}")
    print("-------------------------------------------------------")
    print(f"🎯 Precision (Độ chính xác): {precision:.4f} ({precision*100:.2f}%)")
    print(f"🎯 Recall (Độ phủ phát hiện): {recall:.4f} ({recall*100:.2f}%)")
    print(f"🎯 F1-Score:                  {f1:.4f}")
    print(f"🎯 ROC-AUC Score:            {roc_auc_txt}")
    print("=======================================================")
    print("\n📋 Chi tiết phân loại (Classification Report):")
    print(
        classification_report(
            df["y_true"],
            df["y_pred"],
            target_names=["Bình thường (0)", "Rửa tiền (1)"],
            zero_division=0,
        )
    )


def evaluate_model():
    trans_path = "HI-Sample_Trans.csv"
    if not os.path.exists(trans_path):
        trans_path = "tests/fixtures/aml/HI-Sample_Trans.csv"

    scored_path = _resolve_scored_path()
    print(f"⏳ 1. Đang đọc kết quả chấm điểm từ: {scored_path}...")
    df_scored = pd.read_csv(scored_path)
    df_trans = pd.read_csv(trans_path)

    print("⏳ 2. Ánh xạ nhãn Ground Truth (Is Laundering) từ file giao dịch gốc...")
    labels = _build_laundering_labels(df_trans)

    print("⏳ 3. Tính toán các chỉ số đánh giá Acceptance Criteria...")
    # Báo cáo chính trên test; nếu có train/val thì in thêm
    split_files = [
        ("TEST", "data/scored_test.csv"),
        ("VAL", "data/scored_val.csv"),
        ("TRAIN", "data/scored_train.csv"),
    ]
    reported = False
    for name, path in split_files:
        if os.path.exists(path):
            _report_split(name, pd.read_csv(path), labels)
            reported = True
    if not reported:
        _report_split("SCORED", df_scored, labels)


if __name__ == "__main__":
    evaluate_model()