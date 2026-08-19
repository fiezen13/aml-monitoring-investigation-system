# Rà soát chất lượng tác tử điều tra — 19/08/2026

Công cụ: `scripts/audit_agent_runs.py`. Lấy mẫu cảnh báo theo từng cặp
(bộ phát hiện, nhóm hành vi), chạy đúng quy trình thật, rồi chấm mỗi phiên bằng
những phép kiểm tất định — không hỏi mô hình xem nó tự thấy mình viết tốt chưa.

## Kết quả

| Đợt đo | Số phiên | Chạy xong | Phiên không lỗi |
|---|---:|---:|---:|
| Trước khi sửa | 12 | 75% | 50% |
| Sau đợt sửa 1 | 300 | 87% | 100% |
| Bản cuối | 300 | 99% | 94% |
| Kiểm chứng sau đợt sửa cuối | 80 | 99% | **100%** |

Riêng nhánh địa lý: **0/75 → 75/75** phiên chạy xong.

3 lỗi `HARNESS_ERROR` ở đợt 300 là tranh chấp khoá do công cụ đo chạy 8 luồng
trên cùng một phiên, không phải đường chạy thật — cả 3 đều chạy xong khi gọi
tuần tự như worker vẫn gọi.

## Lỗi đã tìm ra và sửa

| # | Lỗi | Ảnh hưởng |
|---|---|---|
| 1 | `REQUIRED_EVIDENCE` khoá theo `graph`/`ml` — hai giá trị không tồn tại trong bảng `alert` | Khối bổ sung bằng chứng đồ thị **chưa bao giờ chạy**; mọi cảnh báo MEGA-PNA kết luận "chưa kiểm tra được tiền đi qua tài khoản trung gian" |
| 2 | `jurisdiction_signal` / `cross_border_flow` không nhánh nào sinh ra | **5.004/5.004** cảnh báo địa lý trượt phản biện |
| 3 | Cửa sổ đặc trưng rỗng bị viết thành "không có giao dịch nào của tài khoản" | Câu tóm tắt phủ nhận đúng những giao dịch liệt kê ngay bên dưới nó |
| 4 | Bước bổ sung chỉ kiểm tra "đã có bằng chứng hành vi chưa", không kiểm cửa sổ rộng bao nhiêu | Tóm tắt 7 ngày đứng cạnh sổ giao dịch cả tháng — bộ phản biện nêu CONTRADICTION |
| 5 | `_mask_identifiers` xoá cả token toàn chữ số (`next_cursor` = `"50"`) | `5016.80` bị cắt thành ` 16.80` → UNSUPPORTED_CLAIM. Nguyên nhân trượt nhiều nhất |
| 6 | `evidence_index` không kèm mã giao dịch | Bộ phản biện kết luận "giao dịch không có trong danh mục" rồi đánh trượt |
| 7 | Bảng tên nhánh thiếu `mega_pna`, `geo_rule` | "Cảnh báo được nhánh **bằng chứng hiện có** chấm điểm" trên cả 10.004 cảnh báo |
| 8 | Chọn giao dịch dẫn chứng theo số tiền lớn nhất | Cảnh báo hành lang UK→UAE dẫn chứng bằng ba giao dịch nội địa UK |
| 9 | Duyệt mọi bằng chứng giao dịch/hành vi trùng nhau | Cùng một giao dịch được kể hai, ba lần |
| 10 | `GetGraphEvidence` không ghi lại kết quả âm tính | Không phân biệt "đã tra, không có" với "chưa ai tra" |
| 11 | `"chưa kiểm tra được X vì thiếu bằng chứng"` — câu không cho biết phải làm gì | Nay nêu lý do cụ thể, hoặc nói rõ đã tra cứu và không thấy |
| 12 | `Tổng 9,258 đơn vị tiền` — dấu phân cách kiểu Anh | Đọc trong tiếng Việt thành 9,258; bộ đối chiếu số cũng đọc như vậy |

## Còn tồn tại

* **Hai mẫu số cho cùng một hành lang.** Điểm rủi ro tính theo mức nền của toàn
  bộ giao dịch (0,10%), trong khi nhánh này chỉ xét giao dịch xuyên biên giới
  (mức nền 0,31%). Bản giải thích nay nêu **cả hai** kèm tên gọi rõ ràng, nhưng
  công thức chấm điểm chưa đổi — đổi nó là đổi thứ hạng của cả 5.004 cảnh báo.
* `GetTransactions` vẫn lấy 50 dòng gần nhất. Với tài khoản dày giao dịch, một
  hành lang có thật vẫn có thể nằm ngoài trang đầu.
