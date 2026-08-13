# Đặc tả đặc trưng Graph v1

Đây là bộ đặc trưng canonical dùng cho baseline HistGB v1. Mỗi dòng ứng với
`(account_key, as_of_ts)` và cửa sổ giao dịch 7 ngày
`[as_of_ts - 7 ngày, as_of_ts)`. `sample_split` được gán theo thời gian
snapshot, không theo nhãn của từng giao dịch.

## Đặc trưng đồ thị

| Cột | Ý nghĩa |
|---|---|
| `in_degree_7d` | Số đối tác khác nhau chuyển tiền vào tài khoản trong 7 ngày. |
| `out_degree_7d` | Số đối tác khác nhau nhận tiền từ tài khoản trong 7 ngày. |
| `unique_neighbors_7d` | Tổng số đối tác khác nhau theo cả hai chiều. |
| `in_out_degree_ratio_7d` | Tỷ lệ degree vào so với degree ra, có xử lý mẫu số bằng 0. |
| `new_in_counterparty_ratio_7d` | Tỷ lệ đối tác nhận vào chưa từng xuất hiện trước cửa sổ. |
| `new_out_counterparty_ratio_7d` | Tỷ lệ đối tác gửi ra chưa từng xuất hiện trước cửa sổ. |
| `inflow_concentration_7d` | Mức tập trung của dòng tiền vào giữa các đối tác. |
| `outflow_dispersion_7d` | Mức phân tán của dòng tiền ra giữa các đối tác. |
| `history_available` | Có lịch sử trước cửa sổ để tính đặc trưng mới hay không. |
| `history_days_observed` | Số ngày có giao dịch lịch sử trước cửa sổ. |

## Đặc trưng detector

| Cột | Ý nghĩa |
|---|---|
| `fan_in_hit` | FAN_IN có ít nhất một detection cho tài khoản–snapshot. |
| `fan_out_hit` | FAN_OUT có ít nhất một detection. |
| `gather_scatter_hit` | GATHER_SCATTER có ít nhất một detection. |
| `cycle_hit` | CYCLE có ít nhất một detection. |
| `cycle_motif_count` | Số motif CYCLE khác nhau. |
| `cycle_length_min` | Độ dài motif CYCLE ngắn nhất; bằng 0 nếu không có. |
| `cycle_length_max` | Độ dài motif CYCLE dài nhất; bằng 0 nếu không có. |
| `detector_motif_count` | Tổng số motif của các detector cho dòng đó. |

## Quy tắc dữ liệu

- Chỉ dùng các giao dịch có `occurred_at` nằm trong cửa sổ nửa kín nêu trên;
  không dùng giao dịch tương lai.
- Khóa nối chuẩn là `(account_key, as_of_ts)`; `window` luôn là `7d` trong
  artifact v1.
- Các cột nhãn giao dịch không phải là feature. `target_laundering` chỉ dùng
  trong bảng modeling và bằng 1 khi tài khoản tham gia ít nhất một giao dịch
  có nhãn laundering ngay trong cửa sổ hiện tại.
- Các cột hit/count detector là kết quả detector frozen, không phải nhãn học.
- Kiểu thời gian là timestamp có múi giờ; khi truy vấn nên chuẩn hóa về UTC.
