# FIN-07-FUSION-001 — Release hợp nhất Isolation Forest và Graph

## Kết quả

Release `if_graph_fusion_v1` nối hai model đã huấn luyện thành một runtime bundle có thể tái lập:

- Isolation Forest 7 ngày của Hường: 20 đặc trưng hành vi.
- HistGradientBoosting Graph của Hiển: 10 đặc trưng graph và 8 tín hiệu detector.
- Điểm cuối vẫn giữ phân rã đóng góp từng nhánh; không huấn luyện model đầu-cuối thứ ba.

Các artifact chuẩn:

| Artifact | Vai trò |
|---|---|
| `models/fin07_if_graph_fusion_v1.joblib` | Hai estimator, calibration, trọng số, threshold và provenance trong một bundle |
| `data/processed/fusion_scores_v1.parquet` | Điểm hợp nhất theo `(account_key, as_of_ts)` |
| `reports/fusion_release_v1.json` | Checksum, coverage, threshold validation và test metrics |
| `configs/fusion/if_graph_v1.json` | Chính sách release có thể review |

## Các lỗi handoff đã được sửa

Không thể nối trực tiếp hai bảng đầu vào:

1. IF dùng mốc cuối ngày `23:59:59`; Graph dùng đầu ngày tiếp theo `00:00:00`.
   Pipeline cộng đúng một giây cho IF để thống nhất cửa sổ canonical
   `[as_of_ts - 7 ngày, as_of_ts)`.
2. IF có 68.143 khóa `(account_key, as_of_ts)` lặp ở ranh giới split, trong đó nhiều dòng có
   score khác nhau. Pipeline đối chiếu lại vector feature nguồn và ưu tiên bản ghi thuộc cùng
   `sample_split` canonical của Graph.
3. Model Graph pickle từ scikit-learn 1.7.1 ghi module Cython `_loss` không còn import được.
   Builder dùng alias tương thích một lần, kiểm tra prediction khớp score bàn giao với sai số
   tối đa `1e-12`, rồi đóng gói lại cho runtime đã pin.

## Chính sách điểm

Mỗi điểm thành phần được đưa về percentile dựa **chỉ trên train**, dùng lưới 4.097 quantile:

Trọng số khởi đầu là `0.5 / 0.5`, sau đó được chọn trên validation theo lưới bước `0.05`, với
mỗi nhánh giữ tối thiểu `0.1` để release thực sự là bản hợp nhất. Với gói hiện tại, validation chọn:

```text
risk_score = 0.1 × IF_percentile + 0.9 × Graph_percentile
```

Nếu một account-snapshot không có IF, trọng số khả dụng được chuẩn hóa lại và dòng được đánh dấu
`fusion_complete=false`; không tự điền score giả. Threshold được chọn trên validation bằng F1 tốt
nhất trong ngân sách alert tối đa 1%, sau đó mới đánh giá test đúng một lượt.

## Lệnh tái lập

```bash
python scripts/build_fusion_release.py
```

Builder dừng ngay khi thiếu payload, checksum sai, schema sai, model không tái tạo được score bàn
giao, còn khóa trùng sau canonicalization hoặc điểm đóng góp không hợp lệ. Các Parquet hàng trăm MB
được giữ local và bỏ khỏi Git; model bundle, cấu hình, manifest và báo cáo nhỏ được review trong
repository.

## Giới hạn sử dụng

Đây là baseline nghiên cứu trên IBM AML, chưa phải model được kiểm định trên dữ liệu ngân hàng thật.
Score chỉ dùng để xếp hàng ưu tiên điều tra. Mọi cảnh báo vẫn phải giữ lý do thành phần, bằng chứng
Graph/transaction và bước phê duyệt của con người.
