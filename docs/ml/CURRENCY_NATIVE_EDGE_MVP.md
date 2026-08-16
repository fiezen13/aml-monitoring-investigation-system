# FIN-07 — Currency-native policy edge model cho MVP

Tài liệu này là hợp đồng huấn luyện và triển khai của
`fin07_currency_native_policy_edge_v1`. Model chạy bằng CPU và được đóng gói
thành một joblib tự chứa. Đây là model mức **giao dịch**, tách biệt với Fusion
v2 mức ảnh chụp tài khoản và MEGA-PNA.

## Quyết định về tiền tệ

Pipeline ML không quy đổi toàn bộ giao dịch sang USD và không import
`src/data/currency.py`.

- Giữ nguyên `amount_paid_orig` cùng `payment_currency`.
- Giữ nguyên `amount_received_orig` cùng `receiving_currency`.
- Áp `log1p`, rồi z-score riêng cho từng currency. Mean/std chỉ fit trên train
  và được đóng băng trong artifact.
- Các tổng/max tiền vào-ra 24 giờ và 7 ngày chỉ cộng những khoản cùng native
  currency với cạnh đang chấm điểm. Không cộng USD, BTC và EUR vào một tổng.
- Giữ hai category `payment_currency`, `receiving_currency` và cờ
  `cross_currency`.
- Tỷ lệ cùng currency chỉ so các khoản cùng đơn vị. Với giao dịch đổi tiền,
  model dùng `log(amount_received) - log(amount_paid)` được z-score **trong từng
  cặp currency** trên train, kèm cờ cặp đó đã xuất hiện ở train. Đây là tín hiệu
  tỷ lệ của giao dịch, không phải bảng tỷ giá USD.
- Currency mới chưa có thống kê train bị từ chối chấm điểm; phải cập nhật dữ
  liệu và phát hành model version mới. Cặp currency mới giữa hai currency đã
  biết dùng cờ cold-start riêng.

`Payment Format` và giờ trong ngày không nằm trong feature contract. Mọi cửa sổ
đồ thị đều kết thúc trước giao dịch đang chấm một phút; threshold và cấu hình
model chỉ được chọn trên validation. Danh sách hub dùng để giới hạn phép đếm
tam giác cũng chỉ fit trên train, không đọc topology validation/test.

## USD chỉ thuộc rule nghiệp vụ

Ngưỡng pháp lý/nghiệp vụ chạy ngoài model. Một phép đổi sang USD chỉ hợp lệ khi
rule nhận đủ:

```text
amount_native, currency_native, as_of_ts,
fx_rate_to_usd, fx_rate_valid_at, fx_rate_source, fx_rate_id
```

Rule phải chọn quote có `fx_rate_valid_at <= as_of_ts` theo chính sách đã phê
duyệt, lưu lại source/rate/id để audit và từ chối nếu thiếu quote. BTC cũng theo
giá lịch sử đúng `as_of_ts`; tuyệt đối không dùng hằng số BTC = 60.000 USD.
Giá trị USD của rule không được nối ngược vào ma trận feature của model này.

## Huấn luyện release chính thức

Không cần GPU. Trên máy hiện tại, chạy:

```bash
.venv/bin/python scripts/train_currency_native_edge.py \
  --db data/processed/hi_medium.duckdb \
  --model-out models/fin07_currency_native_policy_edge_v1.joblib \
  --report-out reports/edge-benchmark/hi_medium_currency_native_policy_v1.json \
  --scores-out data/processed/edge-policy-v1/hi_medium_test_scores.parquet \
  --threads 4 --memory-limit 18GB --seeds 42 1 2 3 4
```

Artifact joblib chứa estimator, thứ tự 37 feature, categorical indices,
threshold chọn trên validation, vocabulary currency, mean/std train-only, thống
kê từng currency pair, protocol, phiên bản thư viện và provenance. Loader từ
chối artifact sai schema, sai feature order, có static FX hoặc khác phiên bản
scikit-learn.

## Chấm điểm batch cho MVP

```bash
.venv/bin/python scripts/score_currency_native_edge.py \
  --db data/processed/hi_medium.duckdb \
  --model models/fin07_currency_native_policy_edge_v1.joblib \
  --split test \
  --output data/processed/edge-policy-v1/mvp_batch_scores.parquet
```

Parquet đầu ra giữ nguyên bốn trường amount/currency để audit, rồi thêm `score`,
`threshold`, `triggered`, `model_version` và thời điểm chấm. File JSON cạnh nó
ghi checksum model/score và kết quả data-quality gate.

`predict_prepared(frame, bundle)` trong `src/models/currency_native_edge.py` là
API inference cho application sau khi tầng feature state đã dựng các rolling
feature causal. Joblib không tự thay thế feature store: bản MVP batch có thể
dùng DuckDB như script trên; nếu chấm real-time, service phải duy trì cùng state
24 giờ/7 ngày và khóa cùng feature contract trước khi gọi model.

## Kết quả và kiểm chứng

- Báo cáo benchmark máy đọc được:
  `reports/edge-benchmark/hi_medium_currency_native_policy_v1.json`.
- Báo cáo khoa học gồm 15 bảng:
  `reports/edge-benchmark/hi_medium_currency_native_policy_v1.md`.
- Điểm từng giao dịch test: `data/processed/edge-policy-v1/hi_medium_test_scores.parquet`.
- Model release: `models/fin07_currency_native_policy_edge_v1.joblib`.
- Test chống static FX và leakage: `tests/test_models/test_currency_native_edge.py`.

Run chính thức trên 29.336.378 giao dịch HI-Medium hoàn tất trong 3.217,5 giây.
Kết quả F1 test trên 5 seed là **0,712902 ± 0,003846** (sample standard
deviation). Primary release seed 42 có:

| Metric | Giá trị |
|---|---:|
| F1 | 0,718812 |
| PR-AUC | 0,712467 |
| Precision | 0,913928 |
| Recall | 0,592350 |
| True positive | 5.978 |
| False positive | 563 |
| False negative | 4.114 |
| True negative | 5.855.955 |
| Alert | 6.541 / 5.866.610 (0,1115%) |

Ở cùng test split, nhánh lịch sử `policy_compliant` dùng static FX đạt mean F1
0,628399 ± 0,012118. Currency-native release tăng mean F1 **0,084503**, đồng
thời độ dao động giữa seed giảm. So sánh này chỉ cho biết hiệu quả của release
trong repo trên dữ liệu tổng hợp IBM; không phải ước lượng hiệu quả production.

Operating points của primary release:

| Alert được review | Bắt đúng | Precision | Recall |
|---:|---:|---:|---:|
| 1.000 | 991 | 0,9910 | 0,0982 |
| 5.000 | 4.813 | 0,9626 | 0,4769 |
| 12.239 | 7.087 | 0,5791 | 0,7022 |

Artifact đã được load lại sau khi ghi và đối chiếu checksum:

- model: `039b4b0fd5fb669a76c59fb822436626e8ca1d880e2876fabbcbad85431c8ca1`;
- test scores: `269609dcbb3f4d252bf8f5eb5d87f3537c26c32b378cdebee920c74a5338999b`.

Chạy kiểm chứng code:

```bash
.venv/bin/python scripts/render_edge_benchmark_report.py --check
.venv/bin/pytest tests/test_models/test_currency_native_edge.py -q
.venv/bin/ruff check src/models/currency_native_edge.py \
  scripts/train_currency_native_edge.py scripts/score_currency_native_edge.py \
  scripts/render_edge_benchmark_report.py \
  tests/test_models/test_currency_native_edge.py
```

## Nạp release vào giao diện

Loader chỉ chấp nhận PostgreSQL không còn business data cũ; nó kiểm checksum
của DuckDB, joblib, score parquet và benchmark trước khi ghi. Release chỉ đổi
sang `active` sau khi counts giao dịch/score/alert/reason khớp tuyệt đối.

```bash
# Lệnh phá huỷ: chỉ chạy khi đã quyết định bỏ business data PostgreSQL cũ.
docker compose stop api worker postgres
docker compose rm -sf postgres
docker volume rm fin07_postgres_data
docker compose up -d --wait postgres

make load-edge-release
docker compose up -d --build --wait api worker web
```

Release hiện tại phục vụ bốn bề mặt chính:

- Dashboard: population và alert counts của active release;
- Alerts: 6.541 giao dịch vượt threshold cùng ba reason có số;
- Transactions: 5.866.610 giao dịch, hai amount/currency gốc và model score;
- Models: benchmark 5 seeds, policy contract, artifact checksum và threshold.

Không có USD amount được tạo trong loader. `Bitcoin` và các currency dạng tên
đầy đủ được lưu bằng `NUMERIC(38,18)` + `TEXT`; ví dụ giá trị nhỏ nhất của
Bitcoin trong release là `0.000001`.
