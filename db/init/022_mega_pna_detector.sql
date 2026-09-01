-- Nhận cảnh báo từ nhánh MEGA-PNA.
--
-- Ràng buộc cũ chỉ cho ba giá trị ('rule', 'ml', 'graph'). Cảnh báo do MEGA-PNA
-- sinh ra không thuộc loại nào trong đó, nên không nạp được.
--
-- Vì sao KHÔNG dùng lại 'ml':
--
--   * 'ml' đang là Isolation Forest. `GetAnomalyExplanation` tra cảnh báo theo
--     `detector = 'ml'` để lấy phân rã đặc trưng lệch chuẩn — thứ MEGA-PNA không
--     có. Trộn hai nhánh vào một mã sẽ khiến công cụ ấy trả về sai loại giải
--     thích mà không báo lỗi.
--   * Bảng theo dõi và biểu đồ đều nhóm theo `detector`. Gộp lại là mất khả năng
--     nói "cảnh báo này đến từ mô hình đồ thị, không phải mô hình bất thường".
--
-- Ràng buộc cũ được bỏ rồi tạo lại chứ không sửa tại chỗ: PostgreSQL không cho
-- nới CHECK, và tên ràng buộc do hệ thống đặt nên phải tra ra trước.

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
      FROM pg_constraint
     WHERE conrelid = 'alert'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%detector%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE alert DROP CONSTRAINT %I', constraint_name);
    END IF;

    ALTER TABLE alert
        ADD CONSTRAINT alert_detector_check
        CHECK (detector IN ('rule', 'ml', 'graph', 'mega_pna'));
END
$$;

COMMENT ON COLUMN alert.detector IS
    'Nhánh phát hiện đã mở cảnh báo: rule (luật nghiệp vụ), ml (Isolation Forest), '
    'graph (bộ dò mẫu hình), mega_pna (mô hình đồ thị MEGA-PNA).';
