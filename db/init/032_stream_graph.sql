-- 032 · Kho đồ thị TĂNG DẦN cho chế độ streaming (dựng từng cạnh một).
--
-- Vận hành thật ở ngân hàng: giao dịch tới liên tục, mỗi giao dịch = MỘT CẠNH
-- mới. Đồ thị không bao giờ "hoàn chỉnh" như chế độ batch — nó lớn dần. Ba bảng
-- dưới đây là trạng thái SỐNG của đồ thị đó, cập nhật mỗi khi một cạnh tới.
--
-- Vì sao TÁCH khỏi bảng batch (transaction/account):
--   * không đụng 15,6 triệu dòng lịch sử, không vướng FK account→customer,
--   * đồ thị streaming là live; bảng batch là lịch sử — hai vòng đời khác nhau,
--   * khi một cụm chín thành vụ việc (Pha 4) mới vật chất hoá sang bảng case.

-- Cạnh THÔ: mỗi giao dịch một dòng. Dùng để trích ego-subgraph k-hop khi chấm
-- (Pha 2) và để đánh giá/replay (Pha 6). Idempotent theo source_transaction_id.
CREATE TABLE IF NOT EXISTS stream_transaction (
    stream_txn_id         BIGSERIAL PRIMARY KEY,
    source_transaction_id TEXT UNIQUE,
    occurred_at           TIMESTAMPTZ NOT NULL,
    from_account_key      TEXT NOT NULL,
    to_account_key        TEXT NOT NULL,
    amount_paid           NUMERIC(20, 2),
    payment_currency      TEXT,
    amount_received       NUMERIC(20, 2),
    receiving_currency    TEXT,
    payment_format        TEXT,
    -- Nhãn (nếu bộ dữ liệu có) CHỈ để đánh giá, KHÔNG đưa vào đặc trưng model.
    is_laundering         SMALLINT,
    source_dataset        TEXT,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stream_txn_from_time_idx ON stream_transaction (from_account_key, occurred_at DESC);
CREATE INDEX IF NOT EXISTS stream_txn_to_time_idx   ON stream_transaction (to_account_key, occurred_at DESC);

-- Adjacency GỘP (một dòng cho mỗi cặp tài khoản): chính là "đồ thị" cho thuật
-- toán mẫu hình. Distinct out-counterparties của A = COUNT(*) WHERE from=A;
-- fan-in tới B = COUNT(DISTINCT from) WHERE to=B.
CREATE TABLE IF NOT EXISTS stream_edge (
    from_account_key TEXT NOT NULL,
    to_account_key   TEXT NOT NULL,
    txn_count        BIGINT NOT NULL DEFAULT 0,
    total_amount     NUMERIC(24, 2) NOT NULL DEFAULT 0,
    first_seen       TIMESTAMPTZ NOT NULL,
    last_seen        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (from_account_key, to_account_key)
);
CREATE INDEX IF NOT EXISTS stream_edge_to_idx ON stream_edge (to_account_key);

-- Trạng thái node LĂN: đặc trưng rẻ, cập nhật tăng dần mỗi cạnh. Các đặc trưng
-- cần lịch sử (dwell time, median amount…) để Pha sau; ở đây giữ đếm/tổng.
CREATE TABLE IF NOT EXISTS stream_account_state (
    account_key TEXT PRIMARY KEY,
    first_seen  TIMESTAMPTZ NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL,
    in_count    BIGINT NOT NULL DEFAULT 0,
    out_count   BIGINT NOT NULL DEFAULT 0,
    total_in    NUMERIC(24, 2) NOT NULL DEFAULT 0,
    total_out   NUMERIC(24, 2) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
