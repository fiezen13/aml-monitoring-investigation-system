# Bộ dữ liệu IBM Transactions for Anti-Money Laundering

Đặt file CSV của bộ dữ liệu vào **chính thư mục này**. Nội dung thư mục nằm
trong `.gitignore` — file nhỏ nhất đã 250 MB, file lớn nhất hơn 10 GB, và
không bộ dữ liệu nào thuộc về một repo mã nguồn.

Nguồn:
<https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml>

## Cách lấy file

Cách 1 — tải tay từ trang Kaggle rồi kéo file vào đây.

Cách 2 — dùng Kaggle CLI (tuỳ chọn):

```bash
pip install kaggle
# https://www.kaggle.com/settings → Create New Token → lưu ~/.kaggle/kaggle.json
./scripts/aml/download_dataset.sh HI-Small_Trans.csv
```

Không commit `kaggle.json`, và không dán nội dung của nó vào bất kỳ đâu.

## Các file trong bộ dữ liệu

| File | Số giao dịch (xấp xỉ) | Dùng khi |
|---|---|---|
| `HI-Small_Trans.csv` | ~5 triệu | Mặc định. Đủ để chạy hết luồng mà không phải chờ lâu. |
| `LI-Small_Trans.csv` | ~7 triệu | Tỷ lệ nhãn rửa tiền thấp hơn (LI = low illicit). |
| `HI-Medium_Trans.csv` | ~32 triệu | |
| `LI-Medium_Trans.csv` | ~31 triệu | |
| `HI-Large_Trans.csv` | ~180 triệu | Kiểm tra chịu tải. |
| `LI-Large_Trans.csv` | ~176 triệu | |
| `*_Patterns.txt` | — | Mô tả mẫu hình. Giai đoạn này **không** phân tích; chép nguyên trạng lên HDFS bằng `scripts/aml/copy_patterns_to_hdfs.sh`. |

Đổi sang file khác không cần sửa mã, chỉ đổi biến môi trường:

```bash
AML_DATASET_FILE=LI-Medium_Trans.csv docker compose --profile aml run --rm aml-producer
```

## Kiểm tra file trước khi nạp

Lệnh này đọc và chuẩn hoá thật, chỉ không gửi đi đâu — dùng để biết file có
đúng lược đồ không mà chưa cần dựng Kafka:

```bash
python -m src.aml --csv-path data/raw/ibm-aml/HI-Small_Trans.csv --dry-run --max-records 1000 --no-checkpoint
```
