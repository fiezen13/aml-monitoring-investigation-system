-- Hai đại lượng QUY MÔ cho cảnh báo, để hàng đợi xếp được thứ tự khi điểm bão hoà.
--
-- Vì sao không sửa `risk_score`:
--
-- Điểm MEGA-PNA bão hoà ở 100 — 7.226 ô có score_max đúng bằng 1.0, và vùng
-- score_max >= 0,999999 (9.660 ô) chỉ còn 9 giá trị khác nhau. Nhưng đo lại
-- trên nhãn thật thì cả 7.226 ô ấy TRÚNG NHÃN 100%, ở mọi mức số giao dịch.
-- Nghĩa là mô hình không sai và điểm 100 không phải lỗi hiệu chỉnh: những tài
-- khoản ấy đúng là rửa tiền. Sửa một con số đúng thành số khác cho dễ xếp hạng
-- là bịa.
--
-- Cái THẬT SỰ thiếu là thứ tự làm việc: chuyên viên không biết trong 7.226 vụ
-- chắc chắn thì làm vụ nào trước. Hai cột dưới đây là SỰ THẬT ĐO ĐƯỢC về tài
-- khoản, không phải điểm suy ra:
--
--   flagged_txn_count  — số giao dịch của tài khoản vượt ngưỡng cảnh báo
--   flagged_amount     — tổng tiền trên các giao dịch ấy, cộng thô theo nguyên tệ
--
-- Ghép vào khoá sắp xếp, chúng tách 7.226 ô thành 5.573 nhóm phân biệt được.
--
-- `flagged_amount` là NUMERIC(38,2): tổng đã quan sát tới 9,06e11 trên một tài
-- khoản, và đây là phép cộng thô nhiều loại tiền nên không được ép về kiểu hẹp.

ALTER TABLE alert
    ADD COLUMN IF NOT EXISTS flagged_txn_count INTEGER,
    ADD COLUMN IF NOT EXISTS flagged_amount NUMERIC(38, 2);

-- Chỉ mục cho đúng thứ tự mà hàng đợi dùng. Không có nó thì mỗi lần mở trang
-- Cảnh báo là một lần sắp xếp toàn bảng 14 nghìn dòng theo bốn khoá.
DROP INDEX IF EXISTS alert_queue_scale_idx;
CREATE INDEX alert_queue_scale_idx
    ON alert (status, risk_score DESC, flagged_amount DESC NULLS LAST, flagged_txn_count DESC NULLS LAST);

COMMENT ON COLUMN alert.flagged_txn_count IS
    'Số giao dịch vượt ngưỡng cảnh báo. Sự thật đo được, dùng để xếp thứ tự khi điểm bằng nhau.';
COMMENT ON COLUMN alert.flagged_amount IS
    'Tổng tiền trên các giao dịch bị gắn cờ, cộng thô theo nguyên tệ (chưa quy đổi).';
