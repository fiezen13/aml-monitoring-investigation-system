-- 031 · Index cho bộ lọc + sắp xếp giao dịch theo bộ dữ liệu.
--
-- Trang Tra cứu giao dịch lọc theo source_dataset rồi ORDER BY occurred_at DESC.
-- Trên bảng transaction nhiều triệu dòng (IBM + SAML-D), thiếu index này thì
-- count(*) và ORDER BY ... LIMIT phải quét/sắp xếp toàn bảng → treo (~40s+).
--
-- Index tổ hợp (source_dataset, occurred_at DESC) phục vụ CẢ hai:
--   * WHERE source_dataset = '...'                     → dùng tiền tố
--   * WHERE source_dataset = '...' ORDER BY occurred_at DESC LIMIT n → range scan
--
-- Trên prod (Cloud SQL đã có dữ liệu) index này được tạo CONCURRENTLY thủ công;
-- ở đây IF NOT EXISTS để init DB mới có sẵn, và không lặp lại trên prod.

CREATE INDEX IF NOT EXISTS transaction_dataset_time_idx
    ON transaction (source_dataset, occurred_at DESC);
