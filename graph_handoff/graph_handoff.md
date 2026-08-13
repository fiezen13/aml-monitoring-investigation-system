# Bàn giao phần Graph

## Mục đích

Thư mục này là gói bàn giao cuối của pipeline Graph. Các tệp trong đây là bản
v1 đã được đóng băng để nhóm tích hợp có thể đọc trực tiếp mà không phải chạy
lại detector hay huấn luyện lại mô hình.

## Luồng dữ liệu

1. Giao dịch trong DuckDB được gom theo tài khoản và mốc `as_of_ts`.
2. Đặc trưng đồ thị được tính trong cửa sổ 7 ngày.
3. FAN, GATHER_SCATTER và CYCLE tạo detection và evidence ở cấp giao dịch.
4. Các kết quả detector được gom vào bảng tài khoản để huấn luyện baseline.
5. HistGradientBoosting v1 tạo xác suất `graph_score` cho từng tài khoản–mốc thời gian.

Mọi cửa sổ đều dùng dạng nửa kín:

```text
[as_of_ts - 7 ngày, as_of_ts)
```

Giao dịch đúng tại thời điểm bắt đầu được tính; giao dịch đúng tại `as_of_ts`
không được tính. Khóa nối chính giữa các bảng là cặp
`(account_key, as_of_ts)`. `sample_split` cho biết dòng thuộc `train`, `val`
hay `test` theo mốc thời gian đã đóng băng.

## Các tệp trong gói

| Tệp | Nội dung và cách dùng |
|---|---|
| `graph_features_v1.parquet` | Đặc trưng đồ thị canonical ở cấp tài khoản–snapshot. |
| `graph_detection_v1.parquet` | Các detection của FAN/GATHER_SCATTER/CYCLE; dùng để biết mẫu nào bị detector đánh dấu. |
| `graph_evidence_v1.jsonl` | Các giao dịch chứng minh cho detection; dùng khi cần giải thích hoặc kiểm tra alert. |
| `graph_account_modeling_v1.parquet` | Bảng nối đặc trưng đồ thị, hit/count detector và target current-window. |
| `graph_histgb_v1.joblib` | Mô hình HistGradientBoosting v1 đã fit trên train. |
| `graph_scores_v1.parquet` | Điểm mô hình cho các dòng train/val/test, kèm khóa nối, split và hit detector chính. |
| `graph_account_baseline_v1.json` | Cấu hình, giao thức và số liệu baseline đã đóng băng. |
| `graph_pipeline_manifest_v2.json` | Manifest về phiên bản, checksum, số dòng và trạng thái kiểm tra. |
| `graph_feature_spec.md` | Mô tả ngắn các cột đặc trưng canonical. |

## Mô hình và cách tích hợp

HistGradientBoosting v1 dùng 18 cột trong bảng modeling (10 đặc trưng đồ thị
và 8 cột detector), `learning_rate=0.1`, `max_iter=100`,
`max_leaf_nodes=31`, `min_samples_leaf=100`, `l2_regularization=1.0` và
class weight cân bằng. Mô hình chỉ học từ `train`; validation được dùng cho
đánh giá/ngưỡng cảnh báo, còn test chỉ là lần chạy đánh giá cuối.

`graph_score` là xác suất lớp dương do mô hình trả về, chưa phải quyết định
đã phát cảnh báo. Khi tích hợp, hãy nối `graph_scores_v1.parquet` vào bảng
nghiệp vụ bằng `(account_key, as_of_ts)`, giữ lại `sample_split`, và chọn
ngưỡng theo chính sách đã ghi trong baseline report. Các cột hit detector cho
biết lý do nổi bật; muốn xem giao dịch cụ thể thì nối detection với evidence
qua mã detection/evidence và kiểm tra transaction trong cùng cửa sổ 7 ngày.

Không dùng `target_laundering` trong tệp score khi đưa vào hệ thống chấm điểm
thực tế. Target chỉ có trong bảng modeling để đánh giá current-window.

## Kiểm tra tái lập

Trước khi sử dụng, đối chiếu checksum và phiên bản trong manifest. Không đổi
ý nghĩa cửa sổ, khóa nối, detector semantics hoặc mô hình frozen nếu chưa tạo
được một phiên bản mới có manifest riêng.
