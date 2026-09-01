-- 035 · Đồ thị streaming + điểm cho IBM MEGA-PNA (HI-Medium).
--
-- KHÁC nhánh account→account (stream_transaction): MEGA-PNA IBM là đồ thị GIAO DỊCH
-- giữa NODE ĐÃ MÃ HOÁ (from_id/to_id nguyên) với 4 đặc trưng đã format sẵn
-- (Timestamp, Amount Received, Received Currency, Payment Format) — đúng lược đồ mà
-- checkpoint mong đợi. Vì thế dùng bảng riêng, y như Bitcoin có bảng tx riêng (033).

-- Cạnh đã mã hoá, bồi tụ dần (một dòng = một giao dịch IBM đã format).
CREATE TABLE IF NOT EXISTS stream_ibm_edge (
    edge_id           BIGINT PRIMARY KEY,          -- EdgeID gốc (idempotent)
    from_id           BIGINT NOT NULL,             -- node id toàn cục (đã mã hoá)
    to_id             BIGINT NOT NULL,
    ts_raw            DOUBLE PRECISION NOT NULL,    -- Timestamp (đặc trưng thô của model)
    amount_received   DOUBLE PRECISION NOT NULL,
    received_currency DOUBLE PRECISION NOT NULL,    -- đã factorize ở bước format
    payment_format    DOUBLE PRECISION NOT NULL,
    is_laundering     SMALLINT NOT NULL DEFAULT 0,  -- nhãn (để đo pilot; prod có thể NULL)
    arrived_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Đọc theo thứ tự thời gian đến (dựng cửa sổ đồ thị tích luỹ).
CREATE INDEX IF NOT EXISTS stream_ibm_edge_ts_idx ON stream_ibm_edge (ts_raw, edge_id);

-- Điểm mô hình cho từng cạnh IBM (chấm lại được khi đồ thị dày thêm).
CREATE TABLE IF NOT EXISTS stream_ibm_score (
    edge_id       BIGINT PRIMARY KEY REFERENCES stream_ibm_edge (edge_id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    model_score   DOUBLE PRECISION NOT NULL CHECK (model_score >= 0 AND model_score <= 1),
    threshold     DOUBLE PRECISION NOT NULL,
    triggered     BOOLEAN NOT NULL,
    graph_size    INTEGER,               -- số cạnh ngữ cảnh lúc chấm (audit)
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stream_ibm_score_trig_idx ON stream_ibm_score (triggered, model_score DESC);
