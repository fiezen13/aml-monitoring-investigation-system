# Thư mục dữ liệu

Vùng làm việc dữ liệu cục bộ của repo. File lớn nằm trong `.gitignore` và
không bao giờ được commit.

| Thư mục | Nội dung |
|---|---|
| `raw/` | Bộ dữ liệu nguồn tải về, không sửa. Hiện có `ibm-aml/` — xem README trong đó |
| `aml/` | Checkpoint và bản ghi bị từ chối của đường ống nạp AML |

Bộ dữ liệu ngân hàng Việt Nam mô phỏng (`generated/ABM-BANK-*`) đã được gỡ
tháng 08/2026. Dự án dùng bộ IBM AML LI-Small làm nguồn duy nhất cho cả huấn
luyện, đánh giá và trình diễn — lý do ghi trong
[`docs/ml/FIN-07-ML-002`](../docs/ml/FIN-07-ML-002_EDA_Dac_trung_va_Kien_truc.md).

Kết quả EDA nằm ở `artifacts/eda/` và **có** được commit: chỉ vài chục KB, và
tài liệu trích số liệu cùng checksum từ đó nên người đọc kiểm chứng được mà
không cần tải bộ dữ liệu 650 MB.
