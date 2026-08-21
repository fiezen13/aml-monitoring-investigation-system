-- 029 · Gộp 5 vai trò thành 3 (Chuyên viên / Quản lý / Quản trị hệ thống).
--
-- Yêu cầu sản phẩm: chỉ còn ba vai trò. compliance_officer + mlro + auditor được
-- gộp thành "manager" (Quản lý); analyst giữ nguyên là "Chuyên viên"; admin là
-- "Quản trị hệ thống". Nội dung KỸ THUẬT (đánh giá chuẩn, giám sát mô hình, chất
-- lượng dữ liệu, lượt chạy tác tử) chỉ dành cho admin — điều đó thực thi ở tầng
-- API/nav, migration này chỉ lo dữ liệu vai trò.
--
-- Idempotent: chạy lại nhiều lần vẫn cho cùng kết quả. Trên init sạch, file này
-- chạy sau 004 (đã seed đúng vai trò mới) nên chỉ là no-op an toàn.

BEGIN;

-- 1) Nới ràng buộc để nhận cả tên cũ lẫn mới trong lúc chuyển đổi.
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;

-- 2) Gộp vai trò nghiệp vụ cũ về "manager".
UPDATE app_user
   SET role = 'manager'
 WHERE role IN ('compliance_officer', 'mlro', 'auditor');

-- 3) Nhãn tiếng Việt thống nhất theo vai trò.
UPDATE app_user SET role_label = 'Chuyên viên'        WHERE role = 'analyst';
UPDATE app_user SET role_label = 'Quản lý'            WHERE role = 'manager';
UPDATE app_user SET role_label = 'Quản trị hệ thống'  WHERE role = 'admin';

-- 4) Gọn màn đăng nhập: mỗi vai trò hiển thị đúng một tài khoản. Giữ U-001
--    (Quản lý), U-005 (Quản trị hệ thống), U-006 (Chuyên viên) đang hoạt động;
--    các tài khoản demo trùng vai trò còn lại ẩn đi (dữ liệu gán cho họ vẫn còn).
UPDATE app_user SET active = false WHERE user_id IN ('U-002', 'U-003', 'U-004', 'U-007');

-- 5) Chốt lại ràng buộc: chỉ còn ba vai trò hợp lệ.
ALTER TABLE app_user
  ADD CONSTRAINT app_user_role_check CHECK (role IN ('analyst', 'manager', 'admin'));

COMMIT;
