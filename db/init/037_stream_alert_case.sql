-- 037 · Bồi tụ CẢNH BÁO → VỤ VIỆC theo từng cạnh (Pha 4) — nguyên lý vận hành thật.
--
-- Ngân hàng thật: giao dịch tới liên tục, KHÔNG có "cả cụm" sẵn. Mỗi cạnh bị gắn cờ
-- (warm + điểm ≥ ngưỡng) tạo một CẢNH BÁO. Cảnh báo nối nhau qua TÀI KHOẢN CHUNG →
-- gộp dần thành VỤ VIỆC (union-find trên tài khoản). Vụ việc LỚN DẦN từng cạnh.
--
-- Tách hẳn bảng batch (alert/case_) — đây là đường streaming, đúng cách hệ thống chạy.

-- VỤ VIỆC streaming: một cụm tài khoản liên đới, bồi tụ dần.
CREATE TABLE IF NOT EXISTS stream_case (
    case_id       BIGSERIAL PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'open',       -- open | reviewing | closed
    first_seen    TIMESTAMPTZ NOT NULL,               -- cạnh sớm nhất trong vụ
    last_seen     TIMESTAMPTZ NOT NULL,               -- cạnh mới nhất
    alert_count   INTEGER NOT NULL DEFAULT 0,
    account_count INTEGER NOT NULL DEFAULT 0,
    total_amount  NUMERIC(24,2) NOT NULL DEFAULT 0,
    max_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
    laundering_hits INTEGER NOT NULL DEFAULT 0,        -- số cạnh nhãn thật=1 (để đánh giá pilot)
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CẢNH BÁO streaming: một cạnh bị gắn cờ. Gắn vào đúng một vụ việc.
CREATE TABLE IF NOT EXISTS stream_alert (
    alert_id         BIGSERIAL PRIMARY KEY,
    stream_txn_id    BIGINT NOT NULL UNIQUE REFERENCES stream_transaction (stream_txn_id) ON DELETE CASCADE,
    case_id          BIGINT NOT NULL REFERENCES stream_case (case_id) ON DELETE CASCADE,
    from_account_key TEXT NOT NULL,
    to_account_key   TEXT NOT NULL,
    model_score      DOUBLE PRECISION NOT NULL,
    amount           NUMERIC(24,2) NOT NULL DEFAULT 0,
    is_laundering    SMALLINT NOT NULL DEFAULT 0,
    occurred_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stream_alert_case_idx ON stream_alert (case_id);
CREATE INDEX IF NOT EXISTS stream_alert_score_idx ON stream_alert (model_score DESC);

-- Ánh xạ TÀI KHOẢN → VỤ VIỆC (union-find): tra nhanh cạnh mới nối vào vụ nào.
CREATE TABLE IF NOT EXISTS stream_case_account (
    account_key TEXT PRIMARY KEY,
    case_id     BIGINT NOT NULL REFERENCES stream_case (case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS stream_case_account_case_idx ON stream_case_account (case_id);
