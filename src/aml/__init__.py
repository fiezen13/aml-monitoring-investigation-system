"""Luồng nạp dữ liệu giao dịch AML: CSV IBM AML → Kafka → Flink → HDFS.

Gói này chỉ chứa phần **nạp dữ liệu**. Không có logic phát hiện rửa tiền,
chấm điểm rủi ro, học máy hay sinh cảnh báo ở đây — nhãn `is_laundering`
của bộ dữ liệu được mang theo nguyên trạng như một cột dữ liệu bình thường
và không điều khiển bất kỳ nhánh xử lý nào.

Bố cục:

    config.py      cấu hình đọc từ biến môi trường
    schema.py      lược đồ sự kiện chuẩn hoá (canonical) v1.0
    csvsource.py   đọc CSV theo dòng, xử lý hai cột trùng tên `Account`
    transform.py   dòng CSV → sự kiện chuẩn hoá, kèm kiểm tra hợp lệ
    checkpoint.py  điểm dừng để chạy tiếp sau khi producer bị ngắt
    metrics.py     bộ đếm và nhật ký tiến độ
    sink.py        trình gửi Kafka (bọc confluent_kafka)
    replay.py      vòng lặp phát lại, hai chế độ max-throughput và event-time
    cli.py         điểm vào dòng lệnh
"""

SCHEMA_VERSION = "1.0"
