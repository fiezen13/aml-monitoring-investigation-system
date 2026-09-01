-- Quy kết đóng góp đặc trưng theo TỪNG giao dịch cho nhánh Bitcoin.
--
-- Vì sao cần
-- ----------
-- Giải thích cũ xếp đặc trưng theo độ quan trọng TOÀN CỤC (giống nhau cho mọi
-- giao dịch) nên không trả lời được "vì sao CHÍNH giao dịch này bị chấm nghi
-- ngờ". Các cột này lưu phân rã Saabas — đóng góp thực của từng đặc trưng vào
-- P(illicit) của riêng giao dịch đó (tổng đóng góp + bias = đúng điểm số).
--
-- drivers: [{name, label, meaningful, value, contribution}] — top đặc trưng đẩy
-- mạnh nhất. label=null nghĩa là đặc trưng ẩn danh (không đặt tên, không bịa).
-- meaningful_push_share: phần lực đẩy "nghi ngờ" đến từ đặc trưng ĐỌC ĐƯỢC;
-- phần còn lại là ẩn danh — nói thẳng bao nhiêu phần căn cứ không quy được về
-- hành vi.

ALTER TABLE bitcoin_scored_tx
    ADD COLUMN IF NOT EXISTS drivers               JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS meaningful_push_share NUMERIC(5, 4);

COMMENT ON COLUMN bitcoin_scored_tx.drivers IS
    'Phân rã Saabas: đặc trưng nào đẩy điểm của CHÍNH giao dịch này. label=null = '
    'đặc trưng ẩn danh (không bịa nghĩa).';
