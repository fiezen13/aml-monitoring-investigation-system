# Hai nhánh dữ liệu ngoài IBM AML

Nhánh SAML-D (ngân hàng, xuyên biên giới) và nhánh Bitcoin (Elliptic++). Cả hai chạy song song với nhánh IBM AML chính, dùng chung bảng nghiệp vụ.

- [Nhánh SAML-D — phát hiện AML ngân hàng + xuyên biên giới](#nhánh-saml-d-phát-hiện-aml-ngân-hàng-xuyên-biên-giới) — gốc: `docs/samld.md`
- [SAML-D Model — Multi-PNA + Edge Updates (Multi-PNA+EU)](#saml-d-model-multi-pna-edge-updates-multi-pnaeu) — gốc: `docs/samld_model.md`
- [Bitcoin AML — Migrate sang Original Elliptic + ngữ nghĩa DFRWS 2026 (§53)](#bitcoin-aml-migrate-sang-original-elliptic-ngữ-nghĩa-dfrws-2026-53) — gốc: `docs/bitcoin_elliptic_migration.md`
- [Bitcoin AML (Elliptic++) — Explainability Redesign · QA Report](#bitcoin-aml-elliptic-explainability-redesign-qa-report) — gốc: `docs/bitcoin_explainability.md`

## Nhánh SAML-D — phát hiện AML ngân hàng + xuyên biên giới

### Vì sao SAML-D

SAML-D là một trong ba nhánh độc lập của FIN-07 (IBM · SAML-D · Elliptic++), mỗi
nhánh đặc trưng cho một vùng dữ liệu và được đánh giá RIÊNG — **không cộng gộp
điểm**. SAML-D bổ sung phát hiện rửa tiền qua giao dịch ngân hàng có yếu tố
**xuyên biên giới**, với đầy đủ typology, hành lang địa lý, và ngữ cảnh tiền tệ.

Repo có SẴN một nhánh SAML-D dạng luật (`geo_rule`, xếp hạng hành lang). Nhánh
mô tả ở đây là nhánh **học máy đồ thị** (Multi-PNA+EU) — bổ sung chứ không thay
thế; cả hai cùng phục vụ bộ dữ liệu SAML-D.

### Lược đồ dữ liệu

CSV thô: `Time, Date, Sender_account, Receiver_account, Amount, Payment_currency,
Received_currency, Sender_bank_location, Receiver_bank_location, Payment_type,
Is_laundering, Laundering_type`. Quy về canonical trong `src/samld/schema.py`.

Kích thước: 9.504.852 giao dịch · 855.460 tài khoản · 0,104% nhãn dương · 17
typology nghi ngờ · 18 quốc gia · 2022-10-07→2023-08-23. Cross-border 9,8%.

### Biểu diễn đồ thị

Node = tài khoản; cạnh = giao dịch có hướng. **Country là thuộc tính CẠNH**
(ngữ cảnh categorical), không phải node. Quan hệ xuôi + ngược để truyền tin hai
chiều. Chi tiết kiến trúc: [`#saml-d-model-multi-pna-edge-updates-multi-pnaeu`](#saml-d-model-multi-pna-edge-updates-multi-pnaeu).

### Kiến trúc mô hình

Multi-PNA + Edge Updates, **tái dùng nguyên** `src/mega_pna/` (bản gốc IBM
Multi-GNN). Xem `#saml-d-model-multi-pna-edge-updates-multi-pnaeu` cho nguồn gốc, siêu tham số, loss, sampler.

### Quy trình huấn luyện

`python -m scripts.samld_benchmark --config src/samld/config/benchmark.yaml`.
Nạp → chia thời gian → dựng đồ thị → train nhiều seed (early-stop trên val F1) →
baselines → ablation → phân tích → sinh artifacts. Chi tiết vận hành trong
`scripts/samld_benchmark.py`.

### Chia theo thời gian

70/15/15 chronological với ràng buộc `max(train) < min(val) < min(test)` (assert
trong `src/samld/split.py`). Random split chỉ là thí nghiệm phụ, không phải mặc định.

### Phương pháp benchmark

- Chỉ số chính (mất cân bằng): PR-AUC, F1, F2, Precision, Recall, MCC, FPR, ROC-AUC.
  Accuracy chỉ tham chiếu.
- Ngưỡng chọn trên **validation**, đóng băng, áp cho test một lần.
- Baselines: Logistic Regression, XGBoost (tabular trên cùng đặc trưng cạnh),
  và Multi-PNA+EU (đồ thị). Ablation địa lý: full / no_country / no_geography /
  country_shuffle (§18) để tách "học hành vi" khỏi "bám tương quan địa lý".
- Cross-border vs domestic báo cáo riêng (§19); per-typology recall (§21).
- Nhiều seed, mean ± std. (Compute hạn chế thì chạy ít seed hơn và ghi rõ.)

### Tách country / FATF

Model CHỈ biết `sender_country`, `receiver_country`, `cross_border` như **ngữ
cảnh**. KHÔNG có danh sách quốc gia rủi ro FATF/sanctions cứng ở bất kỳ đâu trong
nhánh. Rủi ro pháp lý (FATF, sanctions, jurisdiction) là kiến thức tuân thủ NGOÀI
model, do World Monitor (`/world`) cung cấp riêng — `jurisdiction_risk` hiện để
"unknown", không suy diễn từ tần suất tổng hợp. Agent nhận **model evidence** và
**compliance evidence** như hai nguồn độc lập; không đánh đồng "cross-border" với
"đáng ngờ".

### Luồng inference

Điểm số do model tạo trên đồ thị; đầu ra gồm `aml_probability`, `prediction`,
`threshold`, và `transaction_context` (quốc gia, cross_border, currency_mismatch)
— KHÔNG trả FATF/sanctions/country risk. Xem `src/samld/inference.py`.

### Cách huấn luyện lại

Đặt `SAML-D.csv` ở gốc repo (hoặc trỏ `SAMLD_RAW_CSV`). Chạy benchmark như trên;
checkpoint + threshold + metrics lưu ở `data/models/samld/`. Nạp release vào DB:
`python -m scripts.build_samld_release` (chốt `REL-GRAPH-SAMLD-V1`, status reference).

### Giới hạn đã biết

- SAML-D là **tổng hợp**; hiệu năng rất cao có thể một phần do artifacts của bộ sinh.
- Trường địa lý **không** phải rủi ro FATF hiện hành.
- Kết quả trên SAML-D **không** trực tiếp đại diện cho AML thực tế.
- Số tham chiếu TransXion là để đối chiếu, không phải kết quả repo này.

---

## SAML-D Model — Multi-PNA + Edge Updates (Multi-PNA+EU)

Tài liệu nguồn gốc & tái lập cho nhánh phát hiện AML trên SAML-D.

### Original source

- **IBM Multi-GNN** — <https://github.com/IBM/Multi-GNN>. Kiến trúc MEGA-PNA
  (Multi-Edge Graph Aggregation PNA) với cập nhật cạnh, phân loại **cạnh** trên
  đồ thị giao dịch AML.
- **Benchmark tham chiếu**: TransXion — *A High-Fidelity Graph Benchmark for
  Realistic Anti-Money Laundering*. Trên SAML-D, Multi-PNA+EU đạt (tham chiếu, **KHÔNG**
  phải kết quả repo này): ROC-AUC ≈ 0.999984, AP ≈ 0.994835, F1 ≈ 0.976988.
  Các số này chỉ để đối chiếu; kết quả reproduction của FIN-07 do chính pipeline
  này sinh ra (xem `artifacts/samld/benchmark_report.md`).

### Files reused / adapted

Kiến trúc và vòng huấn luyện **tái dùng nguyên** từ module MEGA-PNA có sẵn của
repo (`src/mega_pna/`) — vốn đã là một hiện thực Multi-PNA+EU bám sát IBM
Multi-GNN. Nhánh SAML-D **không** viết lại GNN; chỉ thêm tầng dữ liệu.

| Thành phần | Nguồn | Ghi chú |
|---|---|---|
| `MegaPna`, `MegaPnaLayer`, `PnaMultiEdgeAggregation` | `src/mega_pna/model.py` | PNA hai chiều (xuôi+ngược), gộp cạnh song song, **edge update MLP** (`edge_updates=True`) |
| Vòng huấn luyện, `LinkNeighborLoader`, ego-id, early-stop | `src/mega_pna/training.py` | `train_one_seed` dùng lại y nguyên |
| Metrics (best-F1 threshold, budget, PR-AUC) | `src/mega_pna/metrics.py` | mở rộng thêm F2/MCC/FPR/Brier ở `src/samld/evaluate.py` |
| `MegaPnaConfig` | `src/mega_pna/config.py` | tái dùng; SAML-D nạp từ YAML |

### Files added (nhánh SAML-D)

`src/samld/`: `schema.py` (canonical + hàng rào rò rỉ nhãn), `data.py` (loader +
dẫn xuất đặc trưng), `split.py` (chia thời gian nghiêm ngặt), `encoders.py`
(one-hot fit-trên-train), `graph_builder.py` (đồ thị → `MegaPnaDataBundle`),
`training.py`, `evaluate.py`, `baselines.py`, `ablation.py`, `plots.py`,
`config/*.yaml`. Script: `scripts/samld_benchmark.py`.

### Graph representation

- **Node = tài khoản**; **cạnh = giao dịch có hướng** (người gửi → người nhận).
- **Country KHÔNG phải node** — là thuộc tính categorical của cạnh (ngữ cảnh).
- Quan hệ xuôi `("node","to","node")` + ngược `("node","rev_to","node")` (đảo chiều)
  để truyền tin hai chiều, khớp `to_hetero` của bản gốc.
- Node feature = vector 1 (cấu trúc); ego-id thêm ở tầng loader.

### Input features (đặc trưng CẠNH) — không có nhãn

Số: `amount_log` (log1p), `hour`, `day_of_week`, `day_of_month`, `elapsed_days`.
Nhị phân: `cross_border` (sender_country≠receiver_country), `currency_mismatch`.
Categorical (one-hot, fit trên train): `payment_type`, `payment_currency`,
`received_currency`, `sender_country`, `receiver_country`.

**Chống rò rỉ**: `Is_laundering`/`Laundering_type` KHÔNG bao giờ là đặc trưng
(kiểm bằng `tests/test_samld/test_leakage.py`). Country **không** map sang bất kỳ
danh sách rủi ro FATF/sanctions cứng nào — chỉ là mã categorical.

### Loss / sampler / threshold

- **Loss**: `CrossEntropyLoss` với trọng số lớp `[1.0, 7.0]` (mất cân bằng ~0,1% dương).
  Hạ tầng hỗ trợ đổi sang focal/pos_weight qua config.
- **Sampler**: `LinkNeighborLoader`, `num_neighbors=[100,100]`, minibatch trên đồ thị
  toàn phần; validation/test giữ phân phối tự nhiên (không undersample).
- **Threshold**: chọn trên **validation** (chiến lược F1, có tuỳ chọn F2/recall-target),
  đóng băng, áp cho test đúng một lần. Không tune trên test.

### Hyperparameters (mặc định, `src/samld/config/default.yaml`)

`hidden_channels=20` (chia hết 5 tower PNA), `num_layers=2`, `dropout=0.28`,
`edge_updates=true`, `reverse_message_passing=true`, `ego_ids=true`,
`batch_size=8192`, `num_neighbors=[100,100]`, `learning_rate=0.0008`,
`epochs=80` (early-stop `patience=8`), `class_weight_laundering=7.0`.

### Split & reproducibility

Chia **theo thời gian** 70/15/15 với ràng buộc `max(train) < min(val) < min(test)`
(assert trong `src/samld/split.py`). Seed đặt cho Python/NumPy/PyTorch/CUDA qua
`set_seed`. Benchmark mặc định 3 seed `[42, 1337, 2026]`, báo cáo mean ± std.

---

## Bitcoin AML — Migrate sang Original Elliptic + ngữ nghĩa DFRWS 2026 (§53)

### CẢI CHÍNH quan trọng
Kết luận trước ("DFRWS không cung cấp mapping; chỉ 1/166 verified") là **SAI**.
Nguồn authoritative: kho companion chính thức của bài báo
  Šafář, Pluskal, Veselý, Ryšavý — *"The Enemy of Reproducibility is Opacity"*,
  Forensic Science International: Digital Investigation, Vol. 57, 302124 (2026).
  https://github.com/nesfit/DeanonymizedEllipticBitcoinDataset

Bài báo **reverse-engineer & validate** ngữ nghĩa: **151/166 phục hồi**
(91/94 local + 60/72 aggregated), **15 chưa giải**: 4, 8, 16, 113–118, 149–154.

### Provenance (không nhầm là "tên chính thức Elliptic")
Elliptic KHÔNG công bố tên. Đây là ngữ nghĩa **RECOVERED_AND_VALIDATED** bởi
Šafář et al.; registry ghi `official_elliptic_semantic=false`, `source=DFRWS 2026`.
15 đặc trưng UNRESOLVED giữ ẩn danh — KHÔNG bịa tên.

### 1. Dataset
`data/raw/elliptic/` — 203.769 tx × 167 cột, 4545 illicit/42019 licit/157205
unknown, 234.355 cạnh. Đúng Weber KDD 2019.

### 2. Feature registry (`elliptic_registry.py`, `feature_registry.json`)
Recovered **151** / Unresolved **15** / Total 166. Categories: TIME 1 ·
TRANSACTION_INTRINSIC 6 · INPUT_VALUE_STATS 6 · OUTPUT_VALUE_STATS 6 ·
INPUT_ADDRESS_HISTORY 36 · OUTPUT_ADDRESS_HISTORY 36 ·
UPSTREAM_TRANSACTION_AGGREGATE 30 · DOWNSTREAM_TRANSACTION_AGGREGATE 30 ·
UNRESOLVED 15. Unresolved indexes: 4, 8, 16, 113, 114, 115, 116, 117, 118, 149,
150, 151, 152, 153, 154.

### 3. Model
RandomForest (100 cây, sqrt, balanced_subsample, seed 42), 166 đặc trưng, chỉ
mẫu có nhãn (unknown KHÔNG thành lớp âm).

### 4. Split
Weber-compatible temporal: train timestep ≤34 (29.894) / test ≥35 (16.670).

### 5. Metrics (test — tái lập benchmark, ưu tiên illicit)
Precision 0.987 · Recall 0.693 · F1 0.814 · ROC-AUC 0.933 · PR-AUC 0.794.
Confusion [[TN 15577, FP 10],[FN 333, TP 750]].

### 6. Leakage status — NOT leakage-free (CẢI CHÍNH §13/§14)
KHÔNG được gọi là "leakage-free". Šafář et al. chỉ ra rò ở CHÍNH bộ dữ liệu:
(A) **preprocessing** — z-score chuẩn hoá tính trên TOÀN bộ dữ liệu, không chỉ
train; (B) **temporal** — đặc trưng cấp-địa-chỉ tính tương đối mốc block
**575,059**, xảy ra SAU giai đoạn test → giao dịch train chứa thông tin tương
lai; (C) **train/test non-independence** — địa chỉ xuất hiện chéo train/test.
→ Metrics ở trên là **tái lập BENCHMARK truyền thống**, KHÔNG phải hiệu năng tổng
quát hoá thực tế (đã ghi vào `training_metadata.json:leakage_status`).

### 7. Explainability (engine đã dựng: `elliptic_explain.py`)
TreeSHAP per-instance (Saabas, `attribution.py`) + registry + percentile train.
Ưu tiên đặc trưng recovered; UNRESOLVED gắn rõ, không bịa. Giá trị standardized +
percentile, KHÔNG giả làm raw BTC (§8/§12).

#### Ví dụ THẬT (top-3 theo |SHAP|)
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

### 8. Files changed
Thêm: `src/bitcoin_aml/elliptic_registry.py` (mapping authoritative),
`src/bitcoin_aml/elliptic_explain.py`, `scripts/train_elliptic_rf.py`,
`data/models/bitcoin_elliptic/*`, `tests/test_bitcoin_aml/{test_elliptic_registry,
test_elliptic_migration}.py`.

### 9. Tests
Registry authoritative (151/15, mapping mốc, unresolved-giữ-ẩn-danh, provenance),
leakage/artifact. Toàn bộ bitcoin suite xanh.

### 10. Remaining (nói thẳng — CHƯA làm end-to-end)
- Wire `elliptic_explain` vào endpoint + rescore tập test vào bảng + migrate UI
  `/crypto` sang Original Elliptic (header 3-chiều + top-reasons semantic + phần
  UNRESOLVED tách riêng). `/crypto` hiện **vẫn** phục vụ nhánh Elliptic++.
- Agent structured schema; deprecate nhánh Elliptic++ (§51 — một nguồn sự thật).
- Đây là công việc lớn còn lại; model + registry + explainability primitives đã
  sẵn sàng và kiểm chứng.

---

## Bitcoin AML (Elliptic++) — Explainability Redesign · QA Report

> Đây là bản ghi tại thời điểm làm, nên một số tên file bên dưới đã đổi:
> `src/bitcoin_aml/explain.py` nay là [`elliptic_explain.py`](../src/bitcoin_aml/elliptic_explain.py)
> (hàm `interpretable_ratio` chuyển sang [`scoring.py`](../src/bitcoin_aml/scoring.py)),
> `tests/test_bitcoin_aml/test_explain.py` đã được thay bằng `test_evidence.py` và
> `test_elliptic_migration.py`, còn `scripts/build_bitcoin_scored.py` nay là
> [`scripts/streaming/pump_bitcoin.py`](../scripts/streaming/pump_bitcoin.py).

Redesign trang giao dịch nhánh Bitcoin để đạt yêu cầu nghiệp vụ AML: tách **điểm
rủi ro** khỏi **chất lượng giải thích**, không bịa nghĩa đặc trưng ẩn danh, phân
biệt **ground-truth** với **model-predicted**, và thu gọn SHAP kỹ thuật.

### 1. Files changed

**Backend**
- `src/bitcoin_aml/explain.py` — thêm `interpretable_ratio` (|SHAP| đọc được),
  `explanation_quality` (HIGH/MEDIUM/LIMITED, tất định), `contribution_breakdown`.
- `scripts/build_bitcoin_scored.py` — dựng tập **known-illicit** (nhãn thật) toàn
  Elliptic++; `_graph_evidence` tách known vs predicted + gắn `known_illicit` cho
  từng láng giềng; tính + lưu `interpretable_ratio`, `explanation_quality`,
  `graph_known_illicit_neighbours`.
- `db/init/027_bitcoin_explanation_quality.sql` — 3 cột mới.
- `src/models/fc_schemas.py`, `src/api/fc_routes.py` — expose các trường mới +
  `neighbour.known_illicit`.

**Frontend**
- `web/src/pages/CryptoPage.tsx` — redesign: hàng đợi gọn → mở ra hồ sơ 6 mục
  A–F; đồ thị thượng-nguồn/mục-tiêu/hạ-nguồn có chú giải; SHAP thu gọn.
- `web/src/api/client.ts` — kiểu `FcBitcoinRow`/`FcBitcoinNeighbour` mới.

**Tests**: `tests/test_bitcoin_aml/test_explain.py` (+6 test).

### 2. Backend explanation schema (structured — nguồn sự thật)

Mỗi giao dịch trong `bitcoin_scored_tx` / `BitcoinScoredRowOut`:

| Trường | Ý nghĩa |
|---|---|
| `illicit_prob`, `risk_level` | ĐIỂM RỦI RO (P(illicit) từ RF). |
| `interpretable_ratio` | Tỷ phần \|SHAP\| từ 7 đặc trưng có nghĩa — "phần giải thích được". |
| `explanation_quality` | HIGH/MEDIUM/LIMITED — tất định, TÁCH khỏi rủi ro. |
| `drivers[]` | Đóng góp Saabas theo từng đặc trưng (ẩn danh → `label=null`). |
| `graph_flagged_neighbours` | Láng giềng **model dự đoán** illicit. |
| `graph_known_illicit_neighbours` | Láng giềng **nhãn thật** illicit (ground truth). |
| `graph_neighbours[].flag` / `.known_illicit` | Dự đoán vs sự thật, tách bạch. |
| `reasons[]`, `caveat` | Câu diễn giải + giới hạn (tất định). |

Giao diện + gợi ý điều tra sinh TỪ các trường này (presentation layer), không
parse ngược từ văn bản.

### 3. How SHAP is calculated

`src/bitcoin_aml/attribution.py::illicit_contributions` — **Saabas** (phân rã
đóng góp chính xác theo cây, cộng dồn trên rừng), cho lớp `illicit`. Đây là đóng
góp per-instance THẬT (không phải feature importance toàn cục). Tổng đóng góp +
bias = P(illicit) của model. UI gọi nó là **"phần giải thích của mô hình"**,
KHÔNG phải "phần trăm nguyên nhân/xác suất phạm tội".

### 4. How explanation quality is calculated (deterministic — không dùng LLM)

`explanation_quality(interpretable, known_illicit_nb, flagged_nb)`:
- **HIGH**: `interpretable ≥ 0.50` **và** có bằng chứng đồ thị.
- **MEDIUM**: `interpretable ≥ 0.35` **hoặc** có ≥1 láng giềng **nhãn thật** illicit.
- **LIMITED**: còn lại (phần lớn ẩn danh, ít bằng chứng đọc được).

Ngưỡng ở `explain.py` (hằng số, chỉnh được). Trên tập cần rà soát: **485 LIMITED
/ 63 MEDIUM / 0 HIGH** — phản ánh trung thực rằng Elliptic++ quá ẩn danh để đạt
HIGH. Chỉ láng giềng *model-dự-đoán* KHÔNG đủ nâng chất lượng (tránh đánh đồng
dự đoán với sự thật).

### 5. Which Elliptic++ features have verified semantics

Model dùng 60 đặc trưng; **7 có nghĩa công bố** (dùng làm nhãn, phần còn lại
tuyệt đối không đặt tên):

`fees`, `size` (byte), `num_input_addresses`, `num_output_addresses`,
`in_BTC_min`, `in_BTC_median`, `out_BTC_min`.

### 6. Which features remain anonymous

**53/60**: `Local_feature_N`, `Aggregate_feature_N` — Elliptic++ KHÔNG công bố ý
nghĩa. UI hiển thị đúng mã kỹ thuật ở phần SHAP thu gọn; ở phần nghiệp vụ gộp
thành một thẻ "tín hiệu mô hình từ đặc trưng ẩn danh" + đếm số lượng. **Không**
suy diễn thành mixer/layering/darknet.

### 7. Known-illicit vs predicted-risk — cách phân biệt

- **Known-illicit**: `tx_id ∈` tập nhãn thật `label==1` của toàn Elliptic++
  (`txs_classes`). Màu đỏ + viền + nhãn "Đã biết bất hợp pháp".
- **Model-predicted**: `predicted==illicit` trên tập test đã chấm. Màu cam + nhãn
  "Model dự đoán rủi ro cao". Đếm riêng (`known` 63 vs `predicted` 27 trên tập
  rà soát). Hai trạng thái KHÔNG bao giờ hiển thị giống nhau.

### 8. Before / after UX

| | Trước | Sau |
|---|---|---|
| Mở đầu | Đoạn văn AI + 5 dòng "đặc trưng ẩn danh" | Hồ sơ 6 mục A–F, tóm tắt trước |
| Rủi ro vs giải thích | Gộp làm một (100/100) | **Hai chỉ số riêng**: rủi ro + chất lượng giải thích |
| Đặc trưng ẩn danh | 5 "reason" ẩn danh | Gộp 1 thẻ "model-only signal" + đếm |
| SHAP | Bày sẵn, lẫn nghiệp vụ | **Thu gọn** sau nút "Xem chi tiết kỹ thuật" |
| Láng giềng | "cũng bị gắn cờ" (mập mờ) | Known (đỏ) vs predicted (cam), có chú giải |
| Đồ thị | Vài chấm | Thượng nguồn → **GIAO DỊCH NÀY** → hạ nguồn + legend |
| "18% lực đẩy nghi ngờ" | Sai hàm ý | "% phần giải thích được của mô hình" |
| Cần kiểm tra tiếp | Không có | Mục F sinh từ bằng chứng thật |

### 9. Screens manually tested (headless browser)

- `/crypto` hàng đợi + mở hồ sơ tx **30204549** (MEDIUM, có láng giềng
  known-illicit — CASE 3): 6 mục A–F render, đồ thị + legend đúng, SHAP thu gọn,
  không lỗi console.
- Xác minh CASE 2 (LIMITED): tx prob 0.99 nhưng quality **Hạn chế** — không bịa lý do.

### 10. Tests executed

- `tests/test_bitcoin_aml`: **26 passed** (+6 mới: interpretable_ratio,
  explanation_quality tách khỏi rủi ro, predicted-only không nâng quality…).
- Regression `bitcoin + api`: **101 passed, 9 skipped**. Web `tsc` sạch.

### 11. Acceptance criteria

AC1 hiểu-không-cần-SHAP ✓ · AC2 ẩn-danh-không-giả-làm-lý-do ✓ · AC3 known≠predicted
✓ · AC4 rủi-ro≠chất-lượng ✓ · AC5 upstream/target/downstream ✓ · AC6 số-liệu-đồ-thị
✓ · AC7 SHAP-thu-gọn ✓ · AC8 không-khẳng-định-rửa-tiền ✓ · AC9 không-bịa-mẫu-hình ✓
· AC10 narrative-từ-structured (tất định, không LLM) ✓ · AC11 chạy-khi-thiếu-đồ-thị
✓ · AC12 responsive/dark-theme ✓.

### 12. Remaining explainability limitations (nói thẳng)

- **Đến từ chính Elliptic++**: 53/60 đặc trưng ẩn danh → chất lượng giải thích
  của phần lớn cảnh báo tối đa là **MEDIUM/LIMITED**, không thể HIGH. Đây là giới
  hạn dữ liệu, không phải lỗi — UI thừa nhận thay vì che.
- *(Đã bổ sung ở lớp Evidence — xem §49 bên dưới)*: multi-hop (BFS ≤3, có trần
  nút) + hop-distance + rule-based topology detector (fan-in/out/gather-scatter/
  chain) — đều đóng khung "cấu trúc quan sát được", không suy diễn tội phạm.
- **Agent narrative**: hiện là template tất định (không gọi LLM) — đúng tinh thần
  "structured evidence là nguồn sự thật"; nếu sau này gắn LLM thì phải theo
  §22–23 (chỉ diễn đạt lại structured evidence, cấm bịa).

---

## Interpretable Investigation Evidence Layer — Deliverables (§49)

Lớp bằng chứng điều tra chạy SONG SONG Random Forest (không thay, không retrain,
không bịa semantic). Ba lớp giữ riêng: **Model risk** · **Investigation evidence**
· **Explainability**.

### A. Files changed
- **Thêm**: `src/bitcoin_aml/evidence.py` (Graph Evidence Engine), `db/init/028_bitcoin_investigation_evidence.sql`, `tests/test_bitcoin_aml/test_evidence.py` (16 test).
- **Sửa**: `scripts/build_bitcoin_scored.py` (precompute evidence), `src/models/fc_schemas.py` + `src/api/fc_routes.py` (expose), `web/src/api/client.ts` + `web/src/pages/CryptoPage.tsx` (3-dim header, badge, multi-hop, topology).

### B. Graph evidence metrics
direct upstream/downstream count · direct/2-hop known-illicit (ground truth) · direct/2-hop model-high-risk (prediction) · nearest_known_illicit_hop & nearest_model_high_risk_hop (BFS ≤3, null nếu ngoài phạm vi) · neighborhood 1/2-hop breakdown (known_illicit/known_licit/model_high_risk/unknown) · mean/max neighbour model-risk · in/out/total degree · max_linear_chain.

### C. Pattern rules (observed structure, KHÔNG phải nhãn tội phạm)
FAN_IN (in≥5 và in>2·out) · FAN_OUT (out≥5 và out>2·in) · GATHER_SCATTER (in≥5 và out≥5) · LINEAR_CHAIN (≥4 giao dịch in≈out≈1). Ngưỡng ở hằng số module (chỉnh được). Toàn tập: LINEAR_CHAIN 1258 · FAN_IN 798 · FAN_OUT 423 · GATHER_SCATTER 37.

### D. Label-leakage protections
- Bằng chứng đồ thị tính **SAU** suy luận, ở module RIÊNG (`evidence.py`) — không chạm predictor.
- Nhãn thật láng giềng chỉ để HIỂN THỊ; KHÔNG là đặc trưng RF.
- Test `test_ground_truth_labels_khong_ro_vao_dac_trung_random_forest`: 60 đặc trưng RF không chứa `neighbor/illicit/label/known/hop/graph_`.

### E. Evidence schema
`graph_evidence` (jsonb): `direct_context` · `ground_truth_exposure` · `model_risk_context` · `neighborhood{one_hop,two_hop}` · `topology{...,observed_patterns}` · `strength`. Kèm `evidence_strength` (NONE/WEAK/MODERATE/STRONG), `evidence_reasons` (badge nguồn), `recommended_steps`.

### F. Agent
Reason builder **tất định** (`evidence_reasons`) là nguồn sự thật, ưu tiên bằng chứng mạnh trước tín hiệu ẩn danh; mỗi lý do mang badge GROUND_TRUTH/GRAPH/MODEL/PREDICTION. Chưa gắn LLM — đúng tinh thần "structured evidence là source of truth"; nếu gắn sau này phải theo §37 (chỉ diễn đạt lại, cấm bịa).

### G. UI before/after
Trước: header 1 chiều (100/100), "5 đặc trưng ẩn danh", đồ thị vài chấm. Sau: **header 3 chiều** (Model risk | Bằng chứng điều tra | Chất lượng giải thích) độc lập; "Vì sao" từ evidence_reasons có **badge nguồn**, ưu tiên phơi nhiễm illicit trước tín hiệu ẩn danh; bằng chứng đồ thị có multi-hop + hop-distance + cấu trúc quan sát; SHAP thu gọn; gợi ý điều tra sinh từ bằng chứng thật.

### H. Performance / caching
Chỉ mục kề dựng **MỘT LẦN** từ txs_edgelist; BFS có trần hop (≤3) + trần nút (600). Precompute toàn bộ vào `bitcoin_scored_tx` bằng script — API chỉ đọc, **không** duyệt đồ thị mỗi request. Chấm lại 16.670 giao dịch: **~12,5s**.

### I. Tests
`test_evidence.py` 16 test (label-leakage, hướng up/down, known≠predicted, hop-distance + null, fan-in/out/gather-scatter/chain, strength, **CASE C** model-thấp-evidence-mạnh, null graph, node-budget cap). Regression bitcoin+api: **117 passed, 9 skipped**. Web `tsc` sạch. Browser: header 3-chiều + badge + multi-hop render, không lỗi console.

### J. Known limitations
- **Model risk ⟂ evidence**: kiểm chứng trên dữ liệu — avg model risk ~0.88 ở CẢ ba mức strength (NONE/MODERATE/STRONG); 441 giao dịch model-thấp vẫn có known-illicit láng giềng (CASE C). Hai lớp thực sự độc lập.
- Chất lượng giải thích tối đa **MEDIUM** (Elliptic++ 53/60 đặc trưng ẩn danh) — giới hạn dữ liệu, UI thừa nhận.
- **Temporal (rapid movement, §17)**: Elliptic++ chỉ có timestep thô nên CHƯA làm — không quy đổi timestep thành "phút".
- **Path-to-illicit highlight & expand-graph control (1/2/3 hop tương tác, §31-32)**: dữ liệu hop-distance + multi-hop đã có ở backend; phần tương tác đồ thị động chưa dựng (đồ thị hiện là 1-hop tĩnh + số liệu multi-hop).
