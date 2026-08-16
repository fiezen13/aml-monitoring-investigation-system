-- Chỉ mục riêng cho màn hình truy vết tài sản mã hoá.
--
-- Màn hình ấy hỏi "giao dịch nào dính tới Bitcoin", và điều kiện là ba nhánh OR
-- trên ba cột khác nhau. Không có chỉ mục nào phục vụ được hình dạng đó, nên
-- PostgreSQL quét toàn bộ 6,1 triệu dòng rồi mới lọc — trên Cloud SQL, một lần
-- mở trang mất gần **200 giây**.
--
-- Chỉ mục một phần là công cụ đúng ở đây: chỉ 264.226 trên 6.119.572 dòng thoả
-- điều kiện (4,3%), nên chỉ mục nhỏ, và điều kiện WHERE của nó khớp *nguyên
-- văn* mệnh đề trong truy vấn — đó là điều kiện để bộ tối ưu chịu dùng nó.
--
-- Sắp theo occurred_at DESC để truy vấn lấy "gần nhất trước" đọc thẳng theo thứ
-- tự chỉ mục, không phải sắp lại.
CREATE INDEX IF NOT EXISTS transaction_crypto_idx
    ON transaction (occurred_at DESC)
    WHERE currency = 'Bitcoin' OR receiving_currency = 'Bitcoin' OR channel = 'BITCOIN';
