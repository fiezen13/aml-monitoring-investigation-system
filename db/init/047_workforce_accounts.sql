-- 047 — đủ người để quy trình chạy được.
--
-- Trước migration này hệ thống chỉ có MỘT chuyên viên và MỘT quản lý đang hoạt
-- động. Hậu quả cụ thể:
--   * không có ai để giao việc cho → cột "Phụ trách" vô nghĩa, thống kê khối
--     lượng chỉ có một dòng;
--   * chốt "người gửi không được tự phê duyệt" khoá cứng mọi hồ sơ do chính
--     quản lý duy nhất nộp — không ai gỡ được, kể cả từ chối.
--
-- Mở lại hai tài khoản demo có sẵn (U-002 quản lý, U-007 chuyên viên) và thêm
-- một chuyên viên nữa. Mật khẩu giữ nguyên quy ước của bộ tài khoản demo đã có
-- trong 004_console_runtime.sql (`demo-password`, PBKDF2-SHA256 200k vòng, salt
-- là hex của chuỗi "fin07-user-<số>") để không phải phát mật khẩu riêng lẻ.
UPDATE app_user SET active = true WHERE user_id IN ('U-002', 'U-007');

INSERT INTO app_user (user_id, name, email, role, role_label, password_salt, password_hash, active)
VALUES ('U-008', 'Vũ Thị Hồng Nhung', 'nhung.vth@velrix.vn', 'analyst', 'Chuyên viên',
        '66696e30372d757365722d303038',
        '5531f93d3168ae625010de3e61d811da97bf572b109cb7a372e6d4bd33544712', true)
ON CONFLICT (user_id) DO NOTHING;
