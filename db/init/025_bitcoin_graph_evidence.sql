-- Bằng chứng đồ thị cho nhánh Bitcoin (Elliptic++).
--
-- Vì sao cần
-- ----------
-- Giải thích cũ chỉ liệt kê vài đặc trưng đọc được (số địa chỉ, kích thước, phí)
-- theo một khuôn cố định, không có bằng chứng riêng cho từng giao dịch. Nhưng
-- Elliptic++ CÓ sẵn đồ thị giao dịch→giao dịch thật (txs_edgelist.csv). Các cột
-- này lưu ngữ cảnh đồ thị 1 chặng của mỗi giao dịch tập test: bậc vào/ra thật,
-- và trong các láng giềng có bao nhiêu cái cũng bị model gắn cờ nghi ngờ.
--
-- QUAN TRỌNG — đây là NGỮ CẢNH, không phải thứ model dùng
-- ------------------------------------------------------
-- Điểm số vẫn do Random Forest chấm bằng ĐẶC TRƯNG. Đồ thị KHÔNG đưa vào model.
-- Các cột này chỉ để chuyên viên nhìn thấy quan hệ thật giữa các giao dịch nghi
-- ngờ; "nằm cạnh giao dịch cũng bị gắn cờ" là tín hiệu để ưu tiên soi, không
-- phải bằng chứng nhân quả.

ALTER TABLE bitcoin_scored_tx
    ADD COLUMN IF NOT EXISTS graph_in_degree        INTEGER,
    ADD COLUMN IF NOT EXISTS graph_out_degree       INTEGER,
    -- Số láng giềng 1 chặng (thuộc tập đã chấm) cũng bị model gắn cờ bất hợp pháp.
    ADD COLUMN IF NOT EXISTS graph_flagged_neighbours INTEGER,
    -- Mẫu láng giềng để vẽ đồ thị lân cận: [{id, dir:'in'|'out', flag:true|false|null}].
    -- flag=null nghĩa là láng giềng nằm ngoài tập đã chấm (không có dự đoán).
    ADD COLUMN IF NOT EXISTS graph_neighbours       JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN bitcoin_scored_tx.graph_flagged_neighbours IS
    'Số láng giềng 1 chặng cũng bị gắn cờ. NGỮ CẢNH cho chuyên viên — model KHÔNG '
    'dùng đồ thị để chấm; điểm số hoàn toàn từ đặc trưng.';
