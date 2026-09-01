"""Train Random Forest trên ORIGINAL Elliptic (Weber KDD 2019) — migrate trung thực.

Ngữ nghĩa đặc trưng lấy từ DFRWS 2026 (151/166 phục hồi — xem elliptic_registry).
Giải thích: tên phục hồi + percentile so với PHÂN PHỐI TRAIN + hướng SHAP.

Split Weber-compatible: train timestep ≤34, test ≥35. LƯU Ý: đây KHÔNG phải
"leakage-free". Šafář et al. (DFRWS 2026) chỉ ra nhiều cơ chế rò ở CHÍNH bộ dữ
liệu (z-score toàn cục, đặc trưng địa chỉ mốc block 575,059 sau test, địa chỉ
chéo train/test). Kết quả ở đây là TÁI LẬP BENCHMARK, không phải tổng quát thực tế.
Chỉ dùng mẫu CÓ NHÃN (illicit/licit); unknown giữ cho graph/inference, KHÔNG làm lớp âm.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, classification_report, confusion_matrix, roc_auc_score

from src.bitcoin_aml.elliptic_registry import write_registry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/elliptic"
OUT = ROOT / "data/models/bitcoin_elliptic"
TRAIN_LAST_TIMESTEP = 34  # ≤34 train, ≥35 test (protocol Weber KDD 2019)
SEED = 42


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    feats = pd.read_csv(DATA / "elliptic_txs_features.csv", header=None)
    classes = pd.read_csv(DATA / "elliptic_txs_classes.csv")
    # Cột: 0=txId, 1=timestep, 2..166 = 165 đặc trưng. Tổng 166 đặc trưng (gồm timestep).
    n_cols = feats.shape[1]
    assert n_cols == 167, f"Kỳ vọng 167 cột (txId+166 đặc trưng), có {n_cols}"
    feats.columns = ["txId", "timestep"] + [f"feature_{i}" for i in range(1, n_cols - 1)]
    feature_cols = ["timestep"] + [f"feature_{i}" for i in range(1, n_cols - 1)]  # 166 đặc trưng
    assert len(feature_cols) == 166

    # Nhãn: 1=illicit→1, 2=licit→0, unknown→bỏ (KHÔNG thành lớp âm).
    classes["txId"] = classes["txId"].astype(str)
    feats["txId"] = feats["txId"].astype(str)
    df = feats.merge(classes, on="txId", how="left")
    label_map = {"1": 1, "2": 0}
    df["label"] = df["class"].astype(str).map(label_map)
    labelled = df[df["label"].notna()].copy()
    labelled["label"] = labelled["label"].astype(int)

    train = labelled[labelled["timestep"] <= TRAIN_LAST_TIMESTEP]
    test = labelled[labelled["timestep"] > TRAIN_LAST_TIMESTEP]
    X_train, y_train = train[feature_cols].to_numpy(np.float32), train["label"].to_numpy()  # noqa: N806
    X_test, y_test = test[feature_cols].to_numpy(np.float32), test["label"].to_numpy()  # noqa: N806

    print(f"labelled={len(labelled)} illicit={int(labelled.label.sum())} | train={len(train)} test={len(test)}")

    rf = RandomForestClassifier(
        n_estimators=100,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=SEED,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    illicit_idx = list(rf.classes_).index(1)
    proba = rf.predict_proba(X_test)[:, illicit_idx]
    pred = (proba >= 0.5).astype(int)

    report = classification_report(y_test, pred, output_dict=True, zero_division=0)
    metrics = {
        "precision_illicit": report["1"]["precision"],
        "recall_illicit": report["1"]["recall"],
        "f1_illicit": report["1"]["f1-score"],
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "pr_auc": float(average_precision_score(y_test, proba)),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "n_train": len(train),
        "n_test": len(test),
        "train_last_timestep": TRAIN_LAST_TIMESTEP,
    }

    # Artifact phân phối TRAIN (cho giải thích percentile) — chỉ từ TRAIN, không rò test.
    # Lưu các mốc percentile + median theo lớp cho từng đặc trưng.
    pct_grid = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    dist = {}
    tr_ill = train[train.label == 1][feature_cols].to_numpy(np.float64)
    tr_lic = train[train.label == 0][feature_cols].to_numpy(np.float64)
    all_tr = train[feature_cols].to_numpy(np.float64)
    for j, name in enumerate(feature_cols):
        dist[name] = {
            "percentiles": {str(p): float(np.percentile(all_tr[:, j], p)) for p in pct_grid},
            "median_licit": float(np.median(tr_lic[:, j])),
            "median_illicit": float(np.median(tr_ill[:, j])),
        }

    joblib.dump(rf, OUT / "elliptic_rf.joblib")
    (OUT / "selected_features.json").write_text(json.dumps(feature_cols, ensure_ascii=False, indent=1))
    (OUT / "evaluation_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1))
    (OUT / "feature_distribution.json").write_text(json.dumps(dist, ensure_ascii=False))
    (OUT / "training_metadata.json").write_text(
        json.dumps(
            {
                "model_id": "bitcoin-elliptic-rf-v1",
                "domain": "bitcoin",
                "dataset": "Elliptic",
                "dataset_version": "original",
                "task": "illicit_transaction_detection",
                "algorithm": "RandomForestClassifier",
                "explainability": "TreeSHAP (per-instance)",
                "semantic_mapping_reference": "Šafář et al., DFRWS USA 2026 (FSI:DI Vol.57, 302124); "
                "companion nesfit/DeanonymizedEllipticBitcoinDataset — "
                "151/166 đặc trưng phục hồi & kiểm chứng, 15 chưa giải.",
                "n_features": 166,
                "split": "Weber-compatible temporal split (train timestep ≤34 / test ≥35)",
                "leakage_status": "NOT leakage-free. Đây là tái lập BENCHMARK Elliptic, KHÔNG phải hiệu năng "
                "tổng quát hoá thực tế. Šafář et al. (DFRWS 2026) chỉ ra: (A) thống kê "
                "z-score chuẩn hoá tính trên TOÀN bộ dữ liệu (không chỉ train); (B) đặc "
                "trưng cấp-địa-chỉ tính tương đối mốc block 575,059 — SAU giai đoạn test; "
                "(C) địa chỉ xuất hiện chéo train/test cho phép model ghi nhớ hành vi thực thể.",
                "seed": SEED,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    write_registry(OUT / "feature_registry.json")

    print(
        "METRICS:",
        json.dumps(
            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items() if k != "confusion_matrix"},
            ensure_ascii=False,
        ),
    )
    print("confusion [[TN,FP],[FN,TP]]:", metrics["confusion_matrix"])
    from src.bitcoin_aml.elliptic_registry import recovery_stats

    print("recovered semantics:", recovery_stats()["recovered"], "/166")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
