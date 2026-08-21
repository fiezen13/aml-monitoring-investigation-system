# Bitcoin AML — Migrate sang Original Elliptic + ngữ nghĩa DFRWS 2026 (§53)

## CẢI CHÍNH quan trọng
Kết luận trước ("DFRWS không cung cấp mapping; chỉ 1/166 verified") là **SAI**.
Nguồn authoritative: kho companion chính thức của bài báo
  Šafář, Pluskal, Veselý, Ryšavý — *"The Enemy of Reproducibility is Opacity"*,
  Forensic Science International: Digital Investigation, Vol. 57, 302124 (2026).
  https://github.com/nesfit/DeanonymizedEllipticBitcoinDataset

Bài báo **reverse-engineer & validate** ngữ nghĩa: **151/166 phục hồi**
(91/94 local + 60/72 aggregated), **15 chưa giải**: 4, 8, 16, 113–118, 149–154.

## Provenance (không nhầm là "tên chính thức Elliptic")
Elliptic KHÔNG công bố tên. Đây là ngữ nghĩa **RECOVERED_AND_VALIDATED** bởi
Šafář et al.; registry ghi `official_elliptic_semantic=false`, `source=DFRWS 2026`.
15 đặc trưng UNRESOLVED giữ ẩn danh — KHÔNG bịa tên.

## 1. Dataset
`data/raw/elliptic/` — 203.769 tx × 167 cột, 4545 illicit/42019 licit/157205
unknown, 234.355 cạnh. Đúng Weber KDD 2019.

## 2. Feature registry (`elliptic_registry.py`, `feature_registry.json`)
Recovered **151** / Unresolved **15** / Total 166. Categories: TIME 1 ·
TRANSACTION_INTRINSIC 6 · INPUT_VALUE_STATS 6 · OUTPUT_VALUE_STATS 6 ·
INPUT_ADDRESS_HISTORY 36 · OUTPUT_ADDRESS_HISTORY 36 ·
UPSTREAM_TRANSACTION_AGGREGATE 30 · DOWNSTREAM_TRANSACTION_AGGREGATE 30 ·
UNRESOLVED 15. Unresolved indexes: 4, 8, 16, 113, 114, 115, 116, 117, 118, 149,
150, 151, 152, 153, 154.

## 3. Model
RandomForest (100 cây, sqrt, balanced_subsample, seed 42), 166 đặc trưng, chỉ
mẫu có nhãn (unknown KHÔNG thành lớp âm).

## 4. Split
Weber-compatible temporal: train timestep ≤34 (29.894) / test ≥35 (16.670).

## 5. Metrics (test — tái lập benchmark, ưu tiên illicit)
Precision 0.987 · Recall 0.693 · F1 0.814 · ROC-AUC 0.933 · PR-AUC 0.794.
Confusion [[TN 15577, FP 10],[FN 333, TP 750]].

## 6. Leakage status — NOT leakage-free (CẢI CHÍNH §13/§14)
KHÔNG được gọi là "leakage-free". Šafář et al. chỉ ra rò ở CHÍNH bộ dữ liệu:
(A) **preprocessing** — z-score chuẩn hoá tính trên TOÀN bộ dữ liệu, không chỉ
train; (B) **temporal** — đặc trưng cấp-địa-chỉ tính tương đối mốc block
**575,059**, xảy ra SAU giai đoạn test → giao dịch train chứa thông tin tương
lai; (C) **train/test non-independence** — địa chỉ xuất hiện chéo train/test.
→ Metrics ở trên là **tái lập BENCHMARK truyền thống**, KHÔNG phải hiệu năng tổng
quát hoá thực tế (đã ghi vào `training_metadata.json:leakage_status`).

## 7. Explainability (engine đã dựng: `elliptic_explain.py`)
TreeSHAP per-instance (Saabas, `attribution.py`) + registry + percentile train.
Ưu tiên đặc trưng recovered; UNRESOLVED gắn rõ, không bịa. Giá trị standardized +
percentile, KHÔNG giả làm raw BTC (§8/§12).

### Ví dụ THẬT (top-3 theo |SHAP|)
```
TX 70333393  label=illicit  P=1.000
  +  Number of unique output addresses            (SHAP +0.039, 10th pct)
  +  Standard deviation of value of output txs     (SHAP +0.034,  1th pct)
  +  Max # outgoing txs of input addresses         (SHAP +0.043,  1th pct)
TX 164687762 label=unknown  P=0.000
  -  Number of outputs                             (SHAP -0.120, 94th pct)
  -  Number of unique output addresses             (SHAP -0.065, 94th pct)
TX 73136178  label=unknown  P=0.980
  +  Max # outgoing txs of input addresses         (SHAP +0.043,  1th pct)
  +  Number of unique output addresses             (SHAP +0.038, 10th pct)
```
(5 giao dịch đầy đủ sinh bằng `elliptic_explain.top_reasons` — tên recovered thật.)

## 8. Files changed
Thêm: `src/bitcoin_aml/elliptic_registry.py` (mapping authoritative),
`src/bitcoin_aml/elliptic_explain.py`, `scripts/train_elliptic_rf.py`,
`data/models/bitcoin_elliptic/*`, `tests/test_bitcoin_aml/{test_elliptic_registry,
test_elliptic_migration}.py`.

## 9. Tests
Registry authoritative (151/15, mapping mốc, unresolved-giữ-ẩn-danh, provenance),
leakage/artifact. Toàn bộ bitcoin suite xanh.

## 10. Remaining (nói thẳng — CHƯA làm end-to-end)
- Wire `elliptic_explain` vào endpoint + rescore tập test vào bảng + migrate UI
  `/crypto` sang Original Elliptic (header 3-chiều + top-reasons semantic + phần
  UNRESOLVED tách riêng). `/crypto` hiện **vẫn** phục vụ nhánh Elliptic++.
- Agent structured schema; deprecate nhánh Elliptic++ (§51 — một nguồn sự thật).
- Đây là công việc lớn còn lại; model + registry + explainability primitives đã
  sẵn sàng và kiểm chứng.
