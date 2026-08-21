# Nhánh SAML-D — phát hiện AML ngân hàng + xuyên biên giới

## Vì sao SAML-D

SAML-D là một trong ba nhánh độc lập của FIN-07 (IBM · SAML-D · Elliptic++), mỗi
nhánh đặc trưng cho một vùng dữ liệu và được đánh giá RIÊNG — **không cộng gộp
điểm**. SAML-D bổ sung phát hiện rửa tiền qua giao dịch ngân hàng có yếu tố
**xuyên biên giới**, với đầy đủ typology, hành lang địa lý, và ngữ cảnh tiền tệ.

Repo có SẴN một nhánh SAML-D dạng luật (`geo_rule`, xếp hạng hành lang). Nhánh
mô tả ở đây là nhánh **học máy đồ thị** (Multi-PNA+EU) — bổ sung chứ không thay
thế; cả hai cùng phục vụ bộ dữ liệu SAML-D.

## Lược đồ dữ liệu

CSV thô: `Time, Date, Sender_account, Receiver_account, Amount, Payment_currency,
Received_currency, Sender_bank_location, Receiver_bank_location, Payment_type,
Is_laundering, Laundering_type`. Quy về canonical trong `src/samld/schema.py`.

Kích thước: 9.504.852 giao dịch · 855.460 tài khoản · 0,104% nhãn dương · 17
typology nghi ngờ · 18 quốc gia · 2022-10-07→2023-08-23. Cross-border 9,8%.

## Biểu diễn đồ thị

Node = tài khoản; cạnh = giao dịch có hướng. **Country là thuộc tính CẠNH**
(ngữ cảnh categorical), không phải node. Quan hệ xuôi + ngược để truyền tin hai
chiều. Chi tiết kiến trúc: [`docs/samld_model.md`](samld_model.md).

## Kiến trúc mô hình

Multi-PNA + Edge Updates, **tái dùng nguyên** `src/mega_pna/` (bản gốc IBM
Multi-GNN). Xem `docs/samld_model.md` cho nguồn gốc, siêu tham số, loss, sampler.

## Quy trình huấn luyện

`python -m scripts.samld_benchmark --config src/samld/config/benchmark.yaml`.
Nạp → chia thời gian → dựng đồ thị → train nhiều seed (early-stop trên val F1) →
baselines → ablation → phân tích → sinh artifacts. Chi tiết vận hành trong
`scripts/samld_benchmark.py`.

## Chia theo thời gian

70/15/15 chronological với ràng buộc `max(train) < min(val) < min(test)` (assert
trong `src/samld/split.py`). Random split chỉ là thí nghiệm phụ, không phải mặc định.

## Phương pháp benchmark

- Chỉ số chính (mất cân bằng): PR-AUC, F1, F2, Precision, Recall, MCC, FPR, ROC-AUC.
  Accuracy chỉ tham chiếu.
- Ngưỡng chọn trên **validation**, đóng băng, áp cho test một lần.
- Baselines: Logistic Regression, XGBoost (tabular trên cùng đặc trưng cạnh),
  và Multi-PNA+EU (đồ thị). Ablation địa lý: full / no_country / no_geography /
  country_shuffle (§18) để tách "học hành vi" khỏi "bám tương quan địa lý".
- Cross-border vs domestic báo cáo riêng (§19); per-typology recall (§21).
- Nhiều seed, mean ± std. (Compute hạn chế thì chạy ít seed hơn và ghi rõ.)

## Tách country / FATF

Model CHỈ biết `sender_country`, `receiver_country`, `cross_border` như **ngữ
cảnh**. KHÔNG có danh sách quốc gia rủi ro FATF/sanctions cứng ở bất kỳ đâu trong
nhánh. Rủi ro pháp lý (FATF, sanctions, jurisdiction) là kiến thức tuân thủ NGOÀI
model, do World Monitor (`/world`) cung cấp riêng — `jurisdiction_risk` hiện để
"unknown", không suy diễn từ tần suất tổng hợp. Agent nhận **model evidence** và
**compliance evidence** như hai nguồn độc lập; không đánh đồng "cross-border" với
"đáng ngờ".

## Luồng inference

Điểm số do model tạo trên đồ thị; đầu ra gồm `aml_probability`, `prediction`,
`threshold`, và `transaction_context` (quốc gia, cross_border, currency_mismatch)
— KHÔNG trả FATF/sanctions/country risk. Xem `src/samld/inference.py`.

## Cách huấn luyện lại

Đặt `SAML-D.csv` ở gốc repo (hoặc trỏ `SAMLD_RAW_CSV`). Chạy benchmark như trên;
checkpoint + threshold + metrics lưu ở `data/models/samld/`. Nạp release vào DB:
`python -m scripts.build_samld_release` (chốt `REL-GRAPH-SAMLD-V1`, status reference).

## Giới hạn đã biết

- SAML-D là **tổng hợp**; hiệu năng rất cao có thể một phần do artifacts của bộ sinh.
- Trường địa lý **không** phải rủi ro FATF hiện hành.
- Kết quả trên SAML-D **không** trực tiếp đại diện cho AML thực tế.
- Số tham chiếu TransXion là để đối chiếu, không phải kết quả repo này.
