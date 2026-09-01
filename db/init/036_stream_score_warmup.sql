-- 036 · Warm-up + ngưỡng streaming theo NGỮ CẢNH cho điểm cạnh (Pha 2+).
--
-- Đã đo (replay streaming thật): điểm GNN streaming bị NÉN vì đồ thị quanh cạnh
-- còn thưa (cold-start). Cách xử lý đúng:
--   * NGƯỠNG STREAMING thấp hơn batch (đo được ~0,003 vs 0,503 cho SAML-D),
--   * TÁCH BUCKET theo bậc endpoint: warm (bậc≥K) chấm bằng model+ngưỡng streaming;
--     cold (tài khoản quá mới) đánh dấu PROVISIONAL và CHẤM LẠI khi đồ thị dày lên.
-- Cột thêm để ghi bối cảnh + trạng thái warm-up.

ALTER TABLE stream_edge_score
    ADD COLUMN IF NOT EXISTS endpoint_min_degree INTEGER,   -- min(bậc nguồn, bậc đích) lúc chấm
    ADD COLUMN IF NOT EXISTS provisional         BOOLEAN NOT NULL DEFAULT FALSE, -- cold, chờ chấm lại
    ADD COLUMN IF NOT EXISTS rescore_count       SMALLINT NOT NULL DEFAULT 0;

ALTER TABLE stream_ibm_score
    ADD COLUMN IF NOT EXISTS endpoint_min_degree INTEGER,
    ADD COLUMN IF NOT EXISTS provisional         BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS rescore_count       SMALLINT NOT NULL DEFAULT 0;

-- Truy vấn nhanh các cạnh provisional để chấm lại khi warm.
CREATE INDEX IF NOT EXISTS stream_edge_score_provisional_idx ON stream_edge_score (provisional) WHERE provisional;
CREATE INDEX IF NOT EXISTS stream_ibm_score_provisional_idx ON stream_ibm_score (provisional) WHERE provisional;
