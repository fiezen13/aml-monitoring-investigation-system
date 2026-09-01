-- 034 · Điểm mô hình cho cạnh streaming (Pha 2 — chấm GNN cục bộ).
--
-- Mỗi cạnh trong stream_transaction, sau khi được chấm bằng neighbor-loader trên
-- đồ thị tích luỹ, lưu một dòng ở đây. Tách bảng để chấm lại được (điểm đổi khi
-- đồ thị dày thêm) mà không đụng bảng cạnh thô.

CREATE TABLE IF NOT EXISTS stream_edge_score (
    stream_txn_id  BIGINT PRIMARY KEY REFERENCES stream_transaction (stream_txn_id) ON DELETE CASCADE,
    model_version  TEXT NOT NULL,
    model_score    DOUBLE PRECISION NOT NULL CHECK (model_score >= 0 AND model_score <= 1),
    threshold      DOUBLE PRECISION NOT NULL,
    triggered      BOOLEAN NOT NULL,
    graph_size     INTEGER,            -- số cạnh đồ thị lúc chấm (audit ngữ cảnh)
    scored_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stream_edge_score_trig_idx ON stream_edge_score (triggered, model_score DESC);
