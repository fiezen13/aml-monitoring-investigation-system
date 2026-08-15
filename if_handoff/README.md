File:
1. `isolation_forest_handoff.md` — hướng dẫn chung của nhóm: lấy dữ liệu từ đâu, không được dùng nhãn khi train, cách chốt ngày chấm điểm, file kết quả ra sao, đo bằng metric nào
2. `docs/feature_spec.md` — mô tả rõ 20 đặc trưng hành vi đã làm (khớp hướng dẫn trên)

### Tóm tắt nhanh

***Model dùng để làm gì***
Isolation Forest xếp hạng tài khoản nào hành vi lạ hơn mặt bằng trong khoảng nhìn lại 7 ngày. Không phải model gắn nhãn kiểu T01–T10. Nó bắt kiểu hành vi như: tiền vào rồi rút nhanh, nhiều người gửi/nhận bất thường, số tiền lặp lại, giao dịch dồn sát nhau…

Extract 20 feature hành vi theo cửa sổ 7 ngày → train Isolation Forest không giám sát → chấm anomaly 0–1 → lấy top-K publish lên Alert Center; điểm cao chỉ nghĩa tài khoản dễ cô lập / ưu tiên xem, rồi mới đưa sang Graph xác minh sâu hơn.

***Input mô hình***
- Dữ liệu giao dịch đã chuẩn hóa trong DuckDB (`aml.duckdb`), tách sẵn train / val / test.
- Từ đó tính 20 đặc trưng hành vi / tài khoản / ngày (chi tiết trong `feature_spec.md`): tần suất giao dịch, tiền vào–ra, rút nhanh, mạng đối tác, phân bố số tiền, nhịp giao dịch…
- Lúc train không đưa cột “có phải rửa tiền không” và không dùng file Patterns.

***Output mô hình***
Mỗi dòng = một tài khoản tại cuối một ngày (giờ UTC), nhìn lại 7 ngày:
- `anomaly_score` từ 0→1 (cao = đáng nghi hơn)
- `top_anomalous_features`: đặc trưng nào lệch so với mặt bằng train
- kèm vector 20 đặc trưng
→ file `if_scores_v1.parquet`.

***Cách chấm***
- Mỗi dòng kết quả = một tài khoản, tại cuối một ngày (giờ UTC), nhìn lại 7 ngày trước đó.
- Lúc train không dùng cột “có phải rửa tiền không” và không dùng file Patterns.
- Kết quả: điểm rủi ro từ 0→1 (cao = đáng nghi hơn) + danh sách đặc trưng nổi bật → file `if_scores_v1.parquet`.

***Chỗ bất thường nằm ở đâu***
Tài khoản điểm cao. Xem thêm danh sách đặc trưng nổi bật để biết lệch ở chỗ nào (rút nhanh, tiền lặp, giao dịch sát nhau…). Chi tiết từng đặc trưng nằm trong `feature_spec.md`.

***Về dữ liệu lệch / cảnh báo giả***
Case rửa tiền rất ít. Nếu bảo hết “không rửa tiền” thì tỉ lệ đúng tổng thể cao, nhưng không bắt được case thật. Muốn bắt nhiều case thật thì phải hạ ngưỡng điểm → ra nhiều cảnh báo sai. Đây là điểm khó chính. Model này hợp để sàng và xếp hàng ưu tiên, chưa phải quyết định cảnh báo cuối. Đo bằng Precision, Recall, PR-AUC, Precision@K (không dùng Accuracy).

***Trạng thái***
Phần đặc tả và quy trình đã làm đúng hướng dẫn (chấm theo từng ngày, 20 đặc trưng, gắn nhãn đúng cửa sổ 7 ngày khi đánh giá). Đã chạy xong Val/Test.
