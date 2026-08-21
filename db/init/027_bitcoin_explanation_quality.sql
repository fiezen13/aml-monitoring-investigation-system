-- Bằng chứng có cấu trúc cho nhánh Bitcoin (Elliptic++): tách CHẤT LƯỢNG GIẢI
-- THÍCH khỏi ĐIỂM RỦI RO, và tách láng giềng ĐÃ BIẾT bất hợp pháp (ground truth)
-- khỏi láng giềng MODEL DỰ ĐOÁN. Nạp giá trị bằng scripts/build_bitcoin_scored.py.
--
-- * interpretable_ratio: tỷ phần |SHAP| đến từ đặc trưng CÓ NGHĨA đã kiểm chứng
--   (7/60 đặc trưng Elliptic++). Đây là "phần giải thích được của model", KHÔNG
--   phải xác suất/nguyên nhân.
-- * explanation_quality: HIGH/MEDIUM/LIMITED — quy tắc tất định (explain.py).
-- * graph_known_illicit_neighbours: số láng giềng 1-chặng có NHÃN THẬT bất hợp
--   pháp; khác với graph_flagged_neighbours (model dự đoán).
ALTER TABLE bitcoin_scored_tx
    ADD COLUMN IF NOT EXISTS interpretable_ratio numeric(5, 4),
    ADD COLUMN IF NOT EXISTS explanation_quality text
        CHECK (explanation_quality IN ('HIGH', 'MEDIUM', 'LIMITED')),
    ADD COLUMN IF NOT EXISTS graph_known_illicit_neighbours integer NOT NULL DEFAULT 0;
