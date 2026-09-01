-- 048 — mã T00: "chưa đối chiếu được nhóm hành vi".
--
-- `alert.typology_code` là NOT NULL và chỉ nhận T01–T10, nên cảnh báo nào chưa
-- chứng minh được nhóm hành vi vẫn buộc phải mang tên một nhóm CÓ THẬT. Mặc
-- định trước đây là T02 "Tài khoản trung chuyển" — rồi bản giải thích đo lại
-- trên cửa sổ giao dịch và nói "chưa khớp dấu hiệu nào": nhãn và lời giải thích
-- đá nhau ngay trên một màn hình, và chuyên viên không biết tin bên nào.
--
-- T00 nói thẳng là chưa đối chiếu được, kèm căn cứ thật của cảnh báo (điểm rủi
-- ro và các yếu tố đóng góp). Đo trên 1.500 cảnh báo IBM: chỉ 1,9% thật sự đạt
-- ngưỡng của T04 mà nhãn cũ gán cho chúng.
--
-- `label.label_typology` giữ nguyên ràng buộc cũ: đó là nhãn HUẤN LUYỆN, phải
-- là một nhóm hành vi có thật thì mới dùng để học được.
ALTER TABLE alert DROP CONSTRAINT IF EXISTS alert_typology_code_check;
ALTER TABLE alert ADD CONSTRAINT alert_typology_code_check
    CHECK (typology_code ~ '^T(0[0-9]|10)$');
