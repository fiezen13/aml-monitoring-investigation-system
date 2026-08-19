# Bitcoin AML — Elliptic++

Nhánh phát hiện rửa tiền Bitcoin, **độc lập** với hai nhánh IBM HI-Medium và
SAML-D. Không gộp giao dịch, không hợp nhất điểm — tác tử nhận kết quả nhánh này
riêng dưới dạng bằng chứng có cấu trúc.

## Dataset

**Elliptic++** (transaction graph): ~203.769 giao dịch, ~234.355 cạnh, 49 bước
thời gian, ~183 đặc trưng ẩn danh. Ba lớp: `1` = illicit, `2` = licit,
`unknown`.

Tải từ repo chính thức: <https://github.com/git-disl/EllipticPlusPlus>

Đặt ba file vào `data/raw/elliptic++/` (hoặc trỏ `--data-dir` / biến môi trường
`BITCOIN_AML_DATA_DIR`):

```
data/raw/elliptic++/
├── txs_features.csv     # txId, Time step, các đặc trưng
├── txs_classes.csv      # txId, class (1/2/unknown)
└── txs_edgelist.csv     # txId1, txId2 (cạnh giao dịch→giao dịch)
```

Loader tự dò tên cột mã/bước-thời-gian và **kiểm chứng** giá trị lớp từ chính
file — gặp giá trị lạ thì báo lỗi, không đoán.

## Reference

Youssef Elmougy, Ling Liu. *Demystifying Fraudulent Transactions and Illicit
Nodes in the Bitcoin Network for Financial Forensics.* ACM SIGKDD 2023.
DOI [10.1145/3580305.3599803](https://doi.org/10.1145/3580305.3599803).

## Model

**Random Forest + tinh gọn đặc trưng.** Cố định theo paper — đây là task tái lập
một phương pháp đã công bố, không dò SOTA. Không thử GCN/GAT/PNA ở nhánh này.

- **Chia theo thời gian** (không random): bước ≤ 34 huấn luyện, > 34 kiểm thử;
  validation cắt từ các bước muộn nhất của khối train. Không để tương lai rò về
  quá khứ.
- **Unknown bị loại** khỏi tập giám sát — không mặc định coi là licit.
- **Tinh gọn đặc trưng** theo độ quan trọng (impurity) tính **trên train**, giữ
  đủ đặc trưng phủ 95% độ quan trọng (trần 60). Không bịa ngữ nghĩa cho đặc
  trưng ẩn danh, không dùng test để chọn đặc trưng.
- **Mất cân bằng lớp** xử lý bằng `class_weight="balanced_subsample"` — không
  SMOTE trước khi chia (tránh rò rỉ).

## Kiến trúc

```
Elliptic++
    ↓
Preprocessing (chia theo thời gian, loại unknown, làm sạch)
    ↓
Feature Refinement (chọn đặc trưng theo importance, trên train)
    ↓
Random Forest
    ↓
Illicit Probability  (predict_proba)
    ↓
Bitcoin AML Result   (bằng chứng có cấu trúc)
    ↓
Agent
```

## Train

```bash
python -m scripts.train_bitcoin_aml
# hoặc: python -m scripts.train_bitcoin_aml --data-dir data/raw/elliptic++ --n-estimators 100
```

Sinh artifact vào `data/models/bitcoin_aml/`:

```
bitcoin_rf.joblib        # mô hình
feature_metadata.json    # danh sách + thứ tự đặc trưng đã chọn, importance
training_metrics.json    # chỉ số thật của lần chạy
model_metadata.json      # phiên bản, seed, phân phối lớp, siêu tham số, tham chiếu
```

## Evaluate

Chỉ số in ra cuối lần train (và lưu vào `training_metrics.json`), lấy **từ mô
hình thật**, không hard-code. Báo cáo (illicit là lớp dương):

```
precision_illicit, recall_illicit, f1_illicit, roc_auc, pr_auc, confusion_matrix
```

## Chốt thành nhánh benchmark

```bash
python -m scripts.build_bitcoin_release
```

Ghi một release vào `edge_model_release`; endpoint `/fc/model-branches` tự nhặt
lên, nên thẻ nhánh Bitcoin xuất hiện cạnh IBM và SAML-D trên trang **Đánh giá
chuẩn** — mỗi nhánh trên vùng đặc trưng riêng, **không cộng gộp**.

## Run inference

Nạp mô hình một lần (singleton theo tiến trình), không đọc lại dataset:

```python
from src.bitcoin_aml.service import get_predictor
from src.bitcoin_aml.schemas import TransactionFeatures

predictor = get_predictor()
result = predictor.predict_one(TransactionFeatures(transaction_id="tx_123", features=[...], timestep=31))
```

`features` phải khớp đúng **số lượng và thứ tự** đặc trưng trong
`feature_metadata.json` (các đặc trưng đã tinh gọn). Sai chiều → lỗi, không chấm
bừa.

## API

```
POST /api/v1/aml/bitcoin/predict
POST /api/v1/aml/bitcoin/predict/batch
```

Ví dụ request:

```json
{ "transaction_id": "tx_123", "features": [0.12, -1.03, 2.5, ...], "timestep": 31 }
```

Ví dụ response (bằng chứng cho tác tử):

```json
{
  "detector": "bitcoin_aml",
  "domain": "bitcoin",
  "dataset": "elliptic++",
  "model": "random_forest_feature_refinement",
  "model_id": "bitcoin-ellipticpp-rf-v1",
  "entity_type": "transaction",
  "transaction_id": "tx_123",
  "prediction": { "label": "illicit", "risk_score": 0.9142, "confidence": 0.9142 },
  "evidence": {
    "timestep": 31,
    "top_features": [ { "feature": "feature_3", "value": 1.24, "importance": 0.08 } ],
    "pattern_evidence": []
  },
  "decision": { "risk_level": "HIGH", "requires_review": true }
}
```

- 503 nếu chưa huấn luyện (thiếu artifact) — khác với 422 do đầu vào sai.
- `risk_score` = `P(illicit)` từ `predict_proba`. **Không** cộng với điểm IBM/SAML-D.

## Agent integration

Kết quả trên là bằng chứng có cấu trúc mà tác tử tiêu thụ riêng theo domain
(banking / bitcoin / country). Nhánh Bitcoin **không** ghi vào bảng
`transaction`/`account` dùng chung như IBM/SAML-D, vì Elliptic++ ẩn danh hoá đặc
trưng (không có tài khoản/số tiền/đối tác thật) — trộn vào sẽ là bịa dữ liệu.

## Cấu hình

Qua biến môi trường (mặc định hợp lý, không hard-code path máy dev):

```
BITCOIN_AML_DATA_DIR          # mặc định data/raw/elliptic++
BITCOIN_AML_ARTIFACT_DIR      # mặc định data/models/bitcoin_aml
BITCOIN_AML_THRESHOLD_MEDIUM  # 0.50
BITCOIN_AML_THRESHOLD_HIGH    # 0.75
BITCOIN_AML_THRESHOLD_CRITICAL# 0.90
```

Ngưỡng là **vận hành** (khi nào đẩy lên rà soát), không phải nhãn ground-truth.

## Giới hạn hiện tại

- **Transaction-level only.** Actor/wallet-level (P2) chưa làm — sẽ dùng
  `wallets_features.csv` / `wallets_classes.csv` với cùng khuôn, giữ riêng
  `wallet_risk` khỏi `transaction_risk`, không tự hợp nhất.
- **Không có nhãn mẫu hình** (fan-in/fan-out/layering) — Elliptic++ không cung
  cấp, nên `pattern_evidence` để trống, có sẵn interface mở rộng sau.
- **Feature importance** là toàn cục (impurity), chưa có SHAP per-prediction.
- Ngữ cảnh đồ thị (`graph.py`) ở mức MVP: láng giềng 1 chặng, bậc vào/ra.
