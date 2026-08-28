-- 044 — Người lập báo cáo SAR.
--
-- Bản PDF xuất ra trước đây in "Người lập (đã gửi): Chưa gửi" — suy ra từ nhật
-- ký kiểm toán, nên khi hồ sơ chưa gửi duyệt thì ô người lập rỗng, và chuyên
-- viên KHÔNG có chỗ nào để tự khai tên/chức danh/đơn vị. Báo cáo gửi cơ quan
-- có thẩm quyền bắt buộc phải nêu người lập và đầu mối liên hệ, nên các trường
-- này phải do người lập tự khai và lưu cùng bản nháp.
--
-- Để NULL = chưa khai; API điền sẵn tên/email của chuyên viên được giao vụ để
-- chuyên viên chỉ phải bổ sung chức danh, phòng ban, điện thoại.
ALTER TABLE sar_draft
    ADD COLUMN IF NOT EXISTS preparer_name       TEXT,
    ADD COLUMN IF NOT EXISTS preparer_title      TEXT,
    ADD COLUMN IF NOT EXISTS preparer_department TEXT,
    ADD COLUMN IF NOT EXISTS preparer_phone      TEXT,
    ADD COLUMN IF NOT EXISTS preparer_email      TEXT,
    ADD COLUMN IF NOT EXISTS prepared_at         TIMESTAMPTZ;

COMMENT ON COLUMN sar_draft.preparer_name IS 'Họ tên người lập báo cáo, do chuyên viên tự khai (NULL = chưa khai).';
COMMENT ON COLUMN sar_draft.prepared_at IS 'Thời điểm người lập ký/khai thông tin lập báo cáo.';
