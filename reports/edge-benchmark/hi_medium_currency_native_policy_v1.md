# Báo cáo benchmark khoa học — HI-Medium Currency-Native Policy v1

> **Trạng thái:** `complete` · **Model:** `fin07_currency_native_policy_edge_v1` · **Tạo lúc:** `2026-08-15T06:26:11.786313+00:00`

## Tóm tắt

Mô hình phân loại từng giao dịch trên IBM AML HI-Medium đạt **F1 = 0.296891 ± 0.013084** trên 5 seed (trung bình ± sample SD). Khoảng 95% dùng phân phối t là **[0.280645, 0.313138]**; khoảng này chỉ mô tả biến thiên do seed, không phải khoảng tin cậy cho hiệu năng production. Primary release seed 42 đạt F1 **0.302181**, PR-AUC **0.237065**, precision **0.434978** và recall **0.231504**.

Nguồn số liệu máy đọc được: [`li_small_currency_native_policy_v1.json`](./li_small_currency_native_policy_v1.json); baseline hồi cứu: [`li_small.json`](./li_small.json). Tất cả bảng dưới đây được sinh từ hai artifact đã khóa, không nhập tay.

## 1. Thiết kế nghiên cứu

**Bảng 1. Thiết kế thí nghiệm và protocol đánh giá.**

| Thành phần | Quy định |
| --- | --- |
| Nhiệm vụ | Binary edge classification: một dòng là một giao dịch |
| Dataset | IBM AML HI-Medium, 29.336.378 giao dịch |
| Chia tập | 60/20/20 theo thứ tự thời gian; không shuffle giữa các tập |
| Tính nhân quả | Cửa sổ graph kết thúc 1 phút trước giao dịch được chấm |
| Chọn model | Tối đa hóa F1 validation của lớp laundering |
| Chọn threshold | Tối đa hóa F1 trên validation; không chọn trên test |
| Đánh giá chính | F1 trung bình ± sample SD trên 5 seed |
| Đánh giá bổ sung | PR-AUC, precision, recall, confusion matrix, operating points |
| Primary release | Seed 42 |
| Model family | scikit-learn HistGradientBoostingClassifier |

**Bảng 2. Phân bố dữ liệu theo temporal split.**

| Tập | Bắt đầu (UTC) | Kết thúc (UTC) | Số dòng | Positive | Negative | Prevalence |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| train | 2022-09-01T00:00:00+00:00 | 2022-09-06T23:43:00+00:00 | 3.671.838 | 1.988 | 3.669.850 | 0,05414% |
| val | 2022-09-06T23:44:00+00:00 | 2022-09-08T21:12:00+00:00 | 1.223.994 | 736 | 1.223.258 | 0,06013% |
| test | 2022-09-08T21:13:00+00:00 | 2022-09-17T15:28:00+00:00 | 1.223.740 | 838 | 1.222.902 | 0,06848% |
| Tổng | — | — | 6.119.572 | 3.562 | 6.116.010 | 0,05821% |

Dữ liệu mất cân bằng rất mạnh; vì vậy accuracy không phải chỉ số chọn model. F1 và PR-AUC được ưu tiên vì tập trung vào lớp laundering hiếm.

**Bảng 3. Data-quality và leakage gates.**

| Kiểm tra | Kết quả | Trạng thái |
| --- | ---: | --- |
| Số dòng kỳ vọng | 6.119.572 | Đạt |
| Số dòng feature | 6.119.572 | Đạt |
| Thiếu currency | 0 | Đạt |
| Currency chưa biết | 0 | Đạt |
| Amount không dương | 0 | Đạt |
| Feature NaN/Inf | 0 | Đạt |
| Fit degree cap | train_only | Đạt |
| Static FX | False | Đạt |

## 2. Policy và feature contract

**Bảng 4. Kiểm chứng policy tiền tệ.**

| Yêu cầu | Kỳ vọng | Artifact ghi nhận |
| --- | --- | --- |
| Amount paid + payment currency gốc | Có | True |
| Amount received + receiving currency gốc | Có | True |
| Static FX trong model | Không | False |
| Chuẩn hóa | Train-only, theo native currency | train-only log1p z-score per native currency |
| Payment format | Không dùng | False |
| Giờ trong ngày | Không dùng | False |
| USD conversion | Chỉ rule ngoài model | external legal/business rules only |

**Bảng 5. Danh mục 37 feature của release.**

| Nhóm | Mô tả | Số feature | Tên feature |
| ---: | --- | ---: | --- |
| 1 | Amount native đã chuẩn hóa | 11 | `paid_log_z`<br>`received_log_z`<br>`a_out_sum_7d_log_z`<br>`a_out_max_7d_log_z`<br>`a_in_sum_7d_log_z`<br>`a_in_max_7d_log_z`<br>`a_in_sum_24h_log_z`<br>`a_max_in_24h_log_z`<br>`b_in_sum_7d_log_z`<br>`b_in_max_7d_log_z`<br>`b_out_sum_7d_log_z` |
| 2 | Currency/category và cờ giao dịch | 7 | `payment_currency_code`<br>`receiving_currency_code`<br>`cross_bank`<br>`cross_currency`<br>`day_of_week`<br>`currency_pair_log_rate_z`<br>`currency_pair_seen_train` |
| 3 | Đếm hoạt động causal 24h/7d | 7 | `a_out_cnt_7d`<br>`a_in_cnt_7d`<br>`b_in_cnt_7d`<br>`b_out_cnt_7d`<br>`a_in_cnt_24h`<br>`a_mins_since_last_in`<br>`b_out_cnt_24h` |
| 4 | Cấu trúc đồ thị | 7 | `fan_in_b`<br>`fan_out_a`<br>`is_new_pair`<br>`n_2cycle`<br>`n_3cycle`<br>`gather_scatter_a`<br>`gather_scatter_b` |
| 5 | Dòng tiền và trạng thái thiếu inflow | 5 | `log_passthrough_ratio_24h`<br>`log_amount_match_24h`<br>`log_balance_ratio_7d`<br>`a_no_inflow_24h`<br>`a_no_inflow_7d` |

Hai feature category là `payment_currency_code` và `receiving_currency_code`, tại zero-based indices `[11, 12]`. Thống kê amount/currency pair và degree cap đều chỉ fit trên train.

## 3. Chọn siêu tham số trên validation

**Bảng 6. Toàn bộ grid-search trials.** Dòng có F1 validation cao nhất được chọn.

| Trial | class_weight | learning_rate | max_iter | max_leaf_nodes | Threshold | Precision | Recall | F1 | PR-AUC | Giây |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | balanced | 0.1 | 200 | 31 | 0.981123 | 0.143836 | 0.114130 | 0.127273 | 0.071548 | 24.2 |
| 2 | balanced | 0.05 | 500 | 63 | 0.979779 | 0.286260 | 0.101902 | 0.150301 | 0.095497 | 67.5 |
| 3 | None | 0.05 | 500 | 63 | 0.082346 | 0.304709 | 0.149457 | 0.200547 | 0.136624 | 59.4 |
| 4 | None | 0.05 | 800 | 127 | 0.056918 | 0.304813 | 0.154891 | 0.205405 | 0.146687 | 134.6 |

Cấu hình khóa: `{"class_weight": null, "learning_rate": 0.05, "max_iter": 800, "max_leaf_nodes": 127}`; threshold primary `0.056918185108`.

## 4. Kết quả test

**Bảng 7. Kết quả test theo từng seed.** Mỗi seed dùng threshold đã chọn trên validation của chính run đó.

| Seed | Threshold | Precision | Recall | F1 | PR-AUC | TP | FP | FN | Alerts |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42 | 0.056918 | 0.434978 | 0.231504 | 0.302181 | 0.237065 | 194 | 252 | 644 | 446 |
| 1 | 0.094115 | 0.609319 | 0.202864 | 0.304387 | 0.239968 | 170 | 109 | 668 | 279 |
| 2 | 0.113833 | 0.609756 | 0.178998 | 0.276753 | 0.229911 | 150 | 96 | 688 | 246 |
| 3 | 0.061960 | 0.437799 | 0.218377 | 0.291401 | 0.232487 | 183 | 235 | 655 | 418 |
| 4 | 0.086559 | 0.599315 | 0.208831 | 0.309735 | 0.244078 | 175 | 117 | 663 | 292 |

**Bảng 8. Thống kê mô tả trên 5 seed.** SD là sample standard deviation (`ddof=1`).

| Metric | Mean | Sample SD | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| F1 | 0.296891 | 0.013084 | 0.276753 | 0.309735 |
| PR-AUC | 0.236702 | 0.005681 | 0.229911 | 0.244078 |
| Precision | 0.538233 | 0.093070 | 0.434978 | 0.609756 |
| Recall | 0.208115 | 0.019546 | 0.178998 | 0.231504 |
| Alert rate | 0.000275 | 0.000073 | 0.000201 | 0.000364 |
| Threshold | 0.082677 | 0.023502 | 0.056918 | 0.113833 |

**Bảng 9. Ma trận nhầm lẫn của primary release (seed 42).**

| Nhãn thực tế | Dự đoán laundering | Dự đoán legitimate | Tổng |
| --- | ---: | ---: | ---: |
| Laundering | 194 | 644 | 838 |
| Legitimate | 252 | 1.222.650 | 1.222.902 |
| Tổng | 446 | 1.223.294 | 1.223.740 |

**Bảng 10. Chỉ số primary release, gồm chỉ số dẫn xuất từ ma trận nhầm lẫn.**

| Metric | Giá trị | Vai trò |
| --- | ---: | --- |
| F1 | 0.302181 | Chỉ số chính của primary seed |
| PR-AUC | 0.237065 | Chất lượng ranking trên dữ liệu lệch lớp |
| Precision / PPV | 0.434978 | Tỷ lệ alert là positive thật |
| Recall / sensitivity | 0.231504 | Tỷ lệ positive được bắt |
| Specificity | 0.999794 | Tỷ lệ legitimate được bỏ qua đúng |
| False-positive rate | 0.000206 | FP / (FP + TN) |
| False-negative rate | 0.768496 | FN / (FN + TP) |
| Negative predictive value | 0.999474 | TN / (TN + FN) |
| Balanced accuracy | 0.615649 | Trung bình sensitivity và specificity |
| Matthews correlation coefficient | 0.316998 | Đo tương quan cân bằng bốn ô confusion matrix |
| Accuracy | 0.999268 | Chỉ tham khảo do lệch lớp mạnh |
| Prevalence | 0,06848% | Positive / toàn bộ test |
| Alert rate | 0,03645% | 446 / 1.223.740 |

**Bảng 11. Operating points trên ranking của primary release.**

| Review budget | Bắt đúng | False alarm | Precision | Recall | % test được review |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 98 | 2 | 0.980000 | 0.116945 | 0,0082% |
| 250 | 160 | 90 | 0.640000 | 0.190931 | 0,0204% |
| 500 | 201 | 299 | 0.402000 | 0.239857 | 0,0409% |
| 1.000 | 230 | 770 | 0.230000 | 0.274463 | 0,0817% |
| 2.500 | 273 | 2.227 | 0.109200 | 0.325776 | 0,2043% |
| 5.000 | 321 | 4.679 | 0.064200 | 0.383055 | 0,4086% |
| 12.239 | 405 | 11.834 | 0.033091 | 0.483294 | 1,0001% |
| 12.237 | 405 | 11.832 | 0.033096 | 0.483294 | 1,0000% |

Operating points trả lời câu hỏi vận hành theo ngân sách review; chúng không thay thế threshold release `0.056918`.

## 5. So sánh và diễn giải

**Bảng 12. So sánh hồi cứu với các nhánh trong repo trên cùng temporal split.** PR-AUC, precision và recall là primary seed 42; F1 là mean ± sample SD trên 5 seed.

| Nhánh | Features | F1 5 seeds | PR-AUC | Precision | Recall | Δ current − nhánh | Policy note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Basic only | 8 | 0.060138 ± 0.004852 | 0.019319 | 0.035444 | 0.139618 | 0.236753 | Legacy; có feature bị policy hiện tại cấm |
| Basic + Graph | 36 | 0.254664 ± 0.011008 | 0.197812 | 0.273543 | 0.218377 | 0.042227 | Legacy; có feature bị policy hiện tại cấm |
| Policy-compliant static-FX | 34 | 0.209450 ± 0.005142 | 0.137478 | 0.350282 | 0.147971 | 0.087441 | Không dùng feature cấm; còn static FX |
| Currency-native policy v1 | 37 | 0.296891 ± 0.013084 | 0.237065 | 0.434978 | 0.231504 | — | Release hiện tại; không static FX |

So với `policy_compliant` static-FX, release mới tăng F1 tuyệt đối **0.087441** (41.75% tương đối). Đây không phải ablation sạch: feature contract và preprocessing khác nhau, nên không quy toàn bộ chênh lệch cho một biến duy nhất.

**Bảng 13. Kết quả công bố trên LI-Small được giữ trong artifact để tham chiếu.**

| Mô hình | F1 công bố | Dataset |
| --- | ---: | --- |
| XGBoost — basic features | 0.0021 | LI-Small |
| LightGBM — basic features | 0.0205 | LI-Small |
| MLP | 0.1459 | LI-Small |
| LightGBM + GFP | 0.2083 | LI-Small |
| XGBoost + GFP | 0.2728 | LI-Small |
| GIN | 0.3309 | LI-Small |
| PNA | 0.3829 | LI-Small |
| GIN + EU | 0.3927 | LI-Small |

Không xếp hạng trực tiếp Bảng 13 với HI-Medium ở Bảng 12: khác dataset và có thể khác pipeline/feature implementation. Các số này chỉ cung cấp bối cảnh phương pháp.

## 6. Khả năng tái lập và provenance

**Bảng 14. Môi trường và thời gian chạy.**

| Thành phần | Giá trị |
| --- | --- |
| Python | 3.14.2 |
| NumPy | 2.5.2 |
| pandas | 3.0.5 |
| scikit-learn | 1.9.0 |
| DuckDB | 1.5.5 |
| joblib | 1.5.3 |
| Wall-clock | 880.3 giây (14.67 phút) |

**Bảng 15. Artifact release và checksum.**

| Artifact | Đường dẫn | Kích thước | SHA-256 |
| --- | --- | --- | --- |
| Model | `models/fin07_currency_native_policy_edge_li_small_v1.joblib` | 5.07 MiB | `6b31b1644d7aa367f12b296781d14a035c96f4c3af42ecf502316adfd648dd85` |
| Test scores | `data/processed/edge-policy-v1/li_small_test_scores.parquet` | 87.56 MiB | `539ba9fbea5ed33d8d963f8f17b94cd09893f5b26cdd5d6dc7be0c3376e79fdd` |
| Benchmark JSON | `reports/edge-benchmark/li_small_currency_native_policy_v1.json` | — | Nguồn của báo cáo này |

Tái tạo hoặc kiểm tra báo cáo:

```bash
.venv/bin/python scripts/render_edge_benchmark_report.py
.venv/bin/python scripts/render_edge_benchmark_report.py --check
```

## 7. Giới hạn nghiên cứu

| Giới hạn | Ảnh hưởng | Cách xử lý khi production |
| --- | --- | --- |
| Dữ liệu IBM AML là synthetic | Không suy rộng trực tiếp sang tỷ lệ bắt AML thật | Shadow evaluation và backtest trên dữ liệu đã gán nhãn nội bộ |
| Chỉ một temporal split | Chưa đo drift theo nhiều giai đoạn | Rolling/forward-chaining evaluation |
| 5 seed cùng một split | SD chỉ đo ngẫu nhiên thuật toán | Không diễn giải CI seed như CI hiệu năng production |
| Threshold tối ưu F1 | Chưa phản ánh chi phí FP/FN cụ thể | Chọn operating point theo review capacity và risk appetite |
| Baseline không phải ablation sạch | Không xác định nhân quả của từng feature/policy change | Chạy controlled ablation cùng preprocessing và seed |
| Chưa calibration report | Score chưa được chứng minh là xác suất hiệu chỉnh | Đo Brier score/reliability và calibrate trên validation |

## 8. Định nghĩa chỉ số

- `Precision = TP / (TP + FP)`.
- `Recall = TP / (TP + FN)`.
- `F1 = 2 × Precision × Recall / (Precision + Recall)`.
- `PR-AUC` là diện tích dưới đường precision–recall từ score liên tục.
- `Sample SD = sqrt(Σ(xᵢ − x̄)² / (n − 1))` với `n = 5`.
- Khoảng 95% mô tả seed dùng `x̄ ± t(0,975; 4) × SD / sqrt(5)`.

Tài liệu phương pháp trong repo: [Benchmark mức giao dịch](../../docs/ml/README.md#benchmark-mức-giao-dịch-edge-level-cho-li-small) và [Currency-native policy edge model](../../docs/ml/README.md#fin-07-currency-native-policy-edge-model-cho-mvp).
