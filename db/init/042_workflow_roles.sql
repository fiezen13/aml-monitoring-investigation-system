-- Dọn quy trình vụ việc về đúng hai vai, và mở lối vào cho "đóng, không báo cáo".
--
-- Ba chuyện được sửa cùng lúc vì chúng là một:
--
-- 1. `DongKhongBaoCao` trước đây KHÔNG CÓ LỐI VÀO NÀO. Nó chỉ được đọc để lọc
--    "vụ đang mở", chưa nơi nào ghi. Hệ quả: một vụ chỉ kết thúc được bằng cách
--    XUẤT SAR — với 14.263 vụ mà đa số là báo động giả thì đó là ngõ cụt.
--
-- 2. Phê duyệt giờ có HAI LOẠI đề xuất, nên phải phân biệt được:
--      'sar'   — chuyên viên nộp hồ sơ nghi vấn (sar_draft_id có giá trị)
--      'close' — chuyên viên đề nghị đóng, không báo cáo (sar_draft_id NULL)
--    Suy từ `sar_draft_id IS NULL` cũng ra, nhưng đó là suy đoán ngầm; hàng đợi
--    của quản lý cần biết mình đang duyệt cái gì mà không phải đoán.
--
-- 3. Sáu trạng thái giữa chuỗi là CHỮ CHẾT: chỉ tới được qua endpoint
--    `POST /cases/{id}/investigate`, mà không giao diện nào gọi. Chúng vẫn hiện
--    trong nhật ký kiểm toán như những giai đoạn thật đã xảy ra. Đã kiểm trên
--    production: 0 vụ đang ở sáu trạng thái ấy, 0 dòng nhật ký nhắc tới chúng.

ALTER TABLE approval
    ADD COLUMN IF NOT EXISTS request_kind TEXT NOT NULL DEFAULT 'sar';

ALTER TABLE approval
    DROP CONSTRAINT IF EXISTS approval_request_kind_check;

ALTER TABLE approval
    ADD CONSTRAINT approval_request_kind_check
    CHECK (request_kind IN ('sar', 'close'));

-- Đề xuất loại 'sar' BẮT BUỘC có bản nháp; loại 'close' thì không được có.
-- Không có ràng buộc này thì một đề nghị đóng vẫn đính kèm được một SAR, và
-- hàng đợi phê duyệt sẽ hiện hai thứ mâu thuẫn trên cùng một dòng.
ALTER TABLE approval
    DROP CONSTRAINT IF EXISTS approval_kind_matches_draft;

ALTER TABLE approval
    ADD CONSTRAINT approval_kind_matches_draft
    CHECK (
        (request_kind = 'sar'   AND sar_draft_id IS NOT NULL) OR
        (request_kind = 'close' AND sar_draft_id IS NULL)
    );

-- Dời vụ việc còn kẹt ở sáu trạng thái sắp gỡ về "Điều tra bổ sung".
--
-- Trên production là 0 vụ, nhưng KHÔNG viết migration dựa vào việc đã kiểm đúng
-- một cơ sở dữ liệu: máy dev, bản khôi phục cũ hay môi trường của đồng nghiệp
-- đều có thể còn sót (máy dev lúc viết migration này còn đúng 1 vụ). Không có
-- bước này thì migration chết giữa chừng ở ALTER bên dưới.
--
-- `DieuTraBoSung` là đích đúng: cả sáu trạng thái ấy đều thuộc cột mốc "Điều
-- tra & phân tích" trong nhật ký kiểm toán, và vụ nằm đó nghĩa là còn phải làm
-- tiếp — không phải đã xong.
UPDATE aml_case
   SET state = 'DieuTraBoSung', updated_at = now()
 WHERE state IN (
        'TruyHoiBangChung', 'PhanTichDoThi', 'DoiChieuTrungPhatPEP',
        'TinhToanBangCongCu', 'LapLuanGanTypology', 'KiemChungBangChung'
       );

-- Siết danh sách trạng thái: bỏ sáu trạng thái chết khỏi ràng buộc để chúng
-- không quay lại bằng đường nào khác.
ALTER TABLE aml_case
    DROP CONSTRAINT IF EXISTS aml_case_state_check;

ALTER TABLE aml_case
    ADD CONSTRAINT aml_case_state_check
    CHECK (state IN (
        'TiepNhanCanhBao',
        'SoanHoSoNghiVan',
        'ChoNguoiPheDuyet',
        'DieuTraBoSung',
        'XuatHoSo',
        'DongKhongBaoCao'
    ));
