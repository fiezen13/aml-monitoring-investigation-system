-- =====================================================================
-- FIN-07 — Lược đồ cơ sở dữ liệu
-- Nguồn: FIN-07-ARC-001 (Hình 6 — mô hình dữ liệu khái niệm)
--        FIN-07-DAT-001 (ánh xạ cột, danh mục nhãn)
--
-- File này chạy tự động khi container postgres khởi tạo volume lần đầu
-- (docker-entrypoint-initdb.d). Muốn dựng lại từ đầu: `make db-reset`.
-- =====================================================================

SET client_min_messages TO WARNING;

-- ---------------------------------------------------------------------
-- 1. Khách hàng và tài khoản
-- ---------------------------------------------------------------------

CREATE TABLE customer (
    customer_id             TEXT        PRIMARY KEY,
    customer_type           TEXT        NOT NULL CHECK (customer_type IN ('individual', 'organisation')),
    prototype               TEXT        NOT NULL CHECK (prototype IN ('salaried', 'household_business', 'enterprise', 'shell_entity')),
    occupation              TEXT        NOT NULL,
    declared_income_band    TEXT        NOT NULL,
    expected_monthly_volume NUMERIC(18, 2) NOT NULL CHECK (expected_monthly_volume >= 0),
    registered_country      CHAR(2)     NOT NULL,
    onboarding_date         DATE        NOT NULL,
    risk_rating             TEXT        NOT NULL CHECK (risk_rating IN ('low', 'medium', 'high')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE customer IS 'Hồ sơ khách hàng suy ra từ hành vi (FIN-07-DAT-001 mục 5). Dữ liệu tổng hợp, không phải khách hàng thật.';
COMMENT ON COLUMN customer.risk_rating IS 'Suy ra từ nguyên mẫu và quốc gia — KHÔNG suy ra từ nhãn rửa tiền (ND1).';

CREATE TABLE account (
    -- account_key = <bank_code>:<account_number>. Ghép mã ngân hàng là bắt buộc:
    -- mã tài khoản trong dataset chỉ duy nhất trong phạm vi một ngân hàng (DAT-001 mục 4.1).
    account_key   TEXT        PRIMARY KEY,
    customer_id   TEXT        NOT NULL REFERENCES customer (customer_id) ON DELETE RESTRICT,
    bank_code     TEXT        NOT NULL,
    account_number TEXT       NOT NULL,
    opened_at     DATE        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'dormant', 'closed')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_key_format CHECK (account_key = bank_code || ':' || account_number),
    CONSTRAINT account_bank_number_unique UNIQUE (bank_code, account_number)
);

CREATE INDEX account_customer_idx ON account (customer_id);

-- ---------------------------------------------------------------------
-- 2. Giao dịch
-- ---------------------------------------------------------------------

CREATE TABLE transaction (
    transaction_id   BIGSERIAL   PRIMARY KEY,
    occurred_at      TIMESTAMPTZ NOT NULL,
    from_account_key TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    to_account_key   TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    amount           NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency         CHAR(3)     NOT NULL,
    amount_received  NUMERIC(18, 2) NOT NULL CHECK (amount_received > 0),
    receiving_currency CHAR(3)   NOT NULL,
    channel          TEXT        NOT NULL,
    remarks          TEXT        NOT NULL DEFAULT '',
    -- Chia tập theo thời gian, không chia ngẫu nhiên (ND2).
    dataset_split    TEXT        NOT NULL CHECK (dataset_split IN ('train', 'validation', 'test')),
    -- Không có cạnh tự trỏ (DAT-001 mục 10).
    CONSTRAINT transaction_no_self_loop CHECK (from_account_key <> to_account_key)
);

COMMENT ON COLUMN transaction.remarks IS 'Nội dung do người dùng cuối nhập. Là DỮ LIỆU, không phải chỉ dẫn (ARC-001 mục 5.2, RK2).';

CREATE INDEX transaction_from_time_idx ON transaction (from_account_key, occurred_at DESC);
CREATE INDEX transaction_to_time_idx   ON transaction (to_account_key, occurred_at DESC);
CREATE INDEX transaction_time_idx      ON transaction (occurred_at DESC);

-- ---------------------------------------------------------------------
-- 3. Nhãn — tách riêng khỏi bảng đặc trưng (ND1, RD1)
--    Mọi bảng/cột trong schema `label` chỉ được dùng ở bước đánh giá.
-- ---------------------------------------------------------------------

CREATE SCHEMA label;

COMMENT ON SCHEMA label IS 'Bốn nhãn độc lập (DAT-001 mục 8). CHỈ dùng để đánh giá; không cột nào ở đây được đưa vào đặc trưng đầu vào mô hình.';

CREATE TABLE label.label_laundering (
    transaction_id BIGINT PRIMARY KEY REFERENCES transaction (transaction_id) ON DELETE CASCADE,
    is_laundering  BOOLEAN NOT NULL
);

CREATE TABLE label.label_typology (
    transaction_id BIGINT NOT NULL REFERENCES transaction (transaction_id) ON DELETE CASCADE,
    typology_code  TEXT   NOT NULL CHECK (typology_code ~ '^T(0[1-9]|10)$'),
    PRIMARY KEY (transaction_id, typology_code)
);

CREATE TABLE label.label_profile_mismatch (
    account_key TEXT PRIMARY KEY REFERENCES account (account_key) ON DELETE CASCADE,
    reason      TEXT NOT NULL
);

COMMENT ON TABLE label.label_profile_mismatch IS 'Nhãn T10 — tài khoản bị tiêm lệch hồ sơ (DAT-001 mục 5.4). Độc lập với label_laundering.';

CREATE TABLE label.label_watchlist_match (
    account_key   TEXT NOT NULL REFERENCES account (account_key) ON DELETE CASCADE,
    list_entry_id TEXT NOT NULL,
    match_type    TEXT NOT NULL CHECK (match_type IN ('exact', 'variant', 'alias', 'near_miss', 'none')),
    PRIMARY KEY (account_key, list_entry_id)
);

COMMENT ON COLUMN label.label_watchlist_match.match_type IS 'near_miss = nhóm "gần giống nhưng vô can" (~2%), là tập để đo tỷ lệ khớp sai (DAT-001 mục 6).';

-- ---------------------------------------------------------------------
-- 4. Danh sách trừng phạt / PEP — có phiên bản (QD7, ND6)
-- ---------------------------------------------------------------------

CREATE TABLE watchlist_version (
    watchlist_version_id TEXT        PRIMARY KEY,
    source               TEXT        NOT NULL,
    loaded_at            TIMESTAMPTZ NOT NULL,
    entry_count          INTEGER     NOT NULL CHECK (entry_count >= 0),
    checksum             TEXT        NOT NULL
);

COMMENT ON TABLE watchlist_version IS 'Giữ tối thiểu ba phiên bản để diễn tập tình huống kiểm toán (DAT-001 mục 7.1).';

CREATE TABLE watchlist_entry (
    list_entry_id        TEXT        PRIMARY KEY,
    watchlist_version_id TEXT        NOT NULL REFERENCES watchlist_version (watchlist_version_id) ON DELETE RESTRICT,
    full_name            TEXT        NOT NULL,
    normalized_name      TEXT        NOT NULL,
    aliases              TEXT[]      NOT NULL DEFAULT '{}',
    entity_type          TEXT        NOT NULL CHECK (entity_type IN ('person', 'organisation')),
    country              CHAR(2),
    list_type            TEXT        NOT NULL CHECK (list_type IN ('sanction', 'pep'))
);

CREATE INDEX watchlist_entry_version_idx    ON watchlist_entry (watchlist_version_id);
CREATE INDEX watchlist_entry_normalized_idx ON watchlist_entry (normalized_name);

-- ---------------------------------------------------------------------
-- 5. Cảnh báo và vụ việc
-- ---------------------------------------------------------------------

-- "case" là từ khoá SQL nên bảng đặt tên aml_case.
CREATE TABLE aml_case (
    case_id            TEXT        PRIMARY KEY,
    subject_account_key TEXT       NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    title              TEXT        NOT NULL,
    -- Tên trạng thái khớp Hình 4 (ARC-001 mục 3.4). Không có cung tắt từ
    -- SoanHoSo thẳng tới XuatHoSo — cưỡng chế ở tầng ứng dụng và kiểm thử đồ thị.
    state              TEXT        NOT NULL DEFAULT 'TiepNhanCanhBao' CHECK (state IN (
                           'TiepNhanCanhBao', 'TruyHoiBangChung', 'PhanTichDoThi',
                           'DoiChieuTrungPhatPEP', 'TinhToanBangCongCu', 'LapLuanGanTypology',
                           'SoanHoSoNghiVan', 'KiemChungBangChung', 'ChoNguoiPheDuyet',
                           'DieuTraBoSung', 'XuatHoSo', 'DongKhongBaoCao')),
    risk_score         NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    priority           TEXT        NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    assigned_to        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX aml_case_state_score_idx ON aml_case (state, risk_score DESC);

CREATE TABLE alert (
    alert_id       TEXT        PRIMARY KEY,
    account_key    TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    transaction_id BIGINT      REFERENCES transaction (transaction_id) ON DELETE SET NULL,
    typology_code  TEXT        NOT NULL CHECK (typology_code ~ '^T(0[1-9]|10)$'),
    detector       TEXT        NOT NULL CHECK (detector IN ('rule', 'ml', 'graph')),
    risk_score     NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    status         TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'grouped', 'closed')),
    -- Gom cảnh báo theo chủ thể: đòn bẩy lớn nhất cho nỗi đau P01 (ARC-001 mục 3.3).
    case_id        TEXT        REFERENCES aml_case (case_id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trả về 50 cảnh báo trong hàng đợi ≤ 500 ms (ARC-001 mục 5.3).
CREATE INDEX alert_queue_idx   ON alert (status, risk_score DESC, created_at DESC);
CREATE INDEX alert_case_idx    ON alert (case_id);
CREATE INDEX alert_account_idx ON alert (account_key);

CREATE TABLE alert_reason (
    alert_reason_id BIGSERIAL   PRIMARY KEY,
    alert_id        TEXT        NOT NULL REFERENCES alert (alert_id) ON DELETE CASCADE,
    factor_code     TEXT        NOT NULL,
    factor_label    TEXT        NOT NULL,
    contribution    NUMERIC(5, 2) NOT NULL,
    weight          NUMERIC(5, 2) NOT NULL,
    UNIQUE (alert_id, factor_code)
);

COMMENT ON TABLE alert_reason IS 'NT7 — mọi cảnh báo phải trả về tối thiểu ba yếu tố đóng góp có giá trị số.';

CREATE INDEX alert_reason_alert_idx ON alert_reason (alert_id);

-- ---------------------------------------------------------------------
-- 6. Bằng chứng — trục của toàn bộ kiến trúc (ARC-001 mục 3.6)
-- ---------------------------------------------------------------------

CREATE TABLE evidence (
    evidence_id   TEXT        PRIMARY KEY,
    case_id       TEXT        NOT NULL REFERENCES aml_case (case_id) ON DELETE RESTRICT,
    source_table  TEXT        NOT NULL,
    source_ref    TEXT        NOT NULL,
    payload       JSONB       NOT NULL,
    retrieved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_hash TEXT        NOT NULL
);

CREATE INDEX evidence_case_idx ON evidence (case_id);

CREATE TABLE sar_draft (
    sar_draft_id TEXT        PRIMARY KEY,
    case_id      TEXT        NOT NULL REFERENCES aml_case (case_id) ON DELETE RESTRICT,
    version      INTEGER     NOT NULL CHECK (version >= 1),
    status       TEXT        NOT NULL CHECK (status IN ('drafting', 'verified', 'submitted_for_approval', 'approved', 'rejected')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, version)
);

CREATE TABLE sar_statement (
    statement_id TEXT    PRIMARY KEY,
    sar_draft_id TEXT    NOT NULL REFERENCES sar_draft (sar_draft_id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL CHECK (ordinal >= 1),
    body         TEXT    NOT NULL,
    UNIQUE (sar_draft_id, ordinal)
);

-- Quan hệ nhiều–nhiều là BẮT BUỘC: một câu dựa trên nhiều bằng chứng,
-- một bằng chứng phục vụ nhiều câu (ARC-001 mục 3.6).
CREATE TABLE sar_statement_evidence (
    statement_id TEXT NOT NULL REFERENCES sar_statement (statement_id) ON DELETE CASCADE,
    evidence_id  TEXT NOT NULL REFERENCES evidence (evidence_id) ON DELETE RESTRICT,
    PRIMARY KEY (statement_id, evidence_id)
);

-- NT1 — hồ sơ có câu không tham chiếu bằng chứng bị chặn ở tầng dịch vụ;
-- view này là cách kiểm chứng bằng một truy vấn duy nhất.
CREATE VIEW uncited_statement AS
SELECT s.statement_id, s.sar_draft_id, s.ordinal, s.body
FROM sar_statement s
LEFT JOIN sar_statement_evidence se ON se.statement_id = s.statement_id
WHERE se.statement_id IS NULL;

COMMENT ON VIEW uncited_statement IS 'NT1 — phải luôn rỗng. Bất kỳ dòng nào ở đây là một câu khẳng định không có bằng chứng.';

-- ---------------------------------------------------------------------
-- 7. Phê duyệt và nhật ký kiểm toán
-- ---------------------------------------------------------------------

CREATE TABLE approval (
    approval_id TEXT        PRIMARY KEY,
    case_id     TEXT        NOT NULL REFERENCES aml_case (case_id) ON DELETE RESTRICT,
    sar_draft_id TEXT       REFERENCES sar_draft (sar_draft_id) ON DELETE RESTRICT,
    decision    TEXT        NOT NULL CHECK (decision IN ('pending', 'approved', 'rejected', 'more_info')),
    decided_by  TEXT,
    -- NT3 — người phê duyệt phải nêu lý do; ràng buộc ở tầng dữ liệu, không chỉ ở UI.
    reason      TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at  TIMESTAMPTZ,
    CONSTRAINT approval_decided_needs_reason CHECK (
        decision = 'pending'
        OR (decided_by IS NOT NULL AND decided_at IS NOT NULL AND reason IS NOT NULL AND length(btrim(reason)) > 0)
    )
);

CREATE INDEX approval_case_idx ON approval (case_id);

CREATE TABLE audit_log (
    audit_id    BIGSERIAL   PRIMARY KEY,
    case_id     TEXT        REFERENCES aml_case (case_id) ON DELETE RESTRICT,
    event_type  TEXT        NOT NULL CHECK (event_type IN (
                    'agent_query', 'alert_raised', 'case_state_changed', 'submitted_for_approval',
                    'approved', 'rejected', 'more_info_requested', 'file_exported', 'case_viewed')),
    actor       TEXT        NOT NULL,
    actor_role  TEXT        NOT NULL CHECK (actor_role IN ('analyst', 'investigator', 'mlro', 'auditor', 'system', 'agent')),
    payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE audit_log IS 'Chỉ ghi thêm. UPDATE và DELETE bị chặn bằng trigger — xem 002_audit_immutability.sql (QD6, NT4).';

CREATE INDEX audit_log_case_time_idx ON audit_log (case_id, occurred_at);
CREATE INDEX audit_log_time_idx      ON audit_log (occurred_at DESC);

-- ---------------------------------------------------------------------
-- 8. Đối chiếu danh sách — kết quả luôn gắn mã phiên bản (QD7)
-- ---------------------------------------------------------------------

CREATE TABLE screening_result (
    screening_id         TEXT        PRIMARY KEY,
    case_id              TEXT        REFERENCES aml_case (case_id) ON DELETE RESTRICT,
    account_key          TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    list_entry_id        TEXT        NOT NULL REFERENCES watchlist_entry (list_entry_id) ON DELETE RESTRICT,
    watchlist_version_id TEXT        NOT NULL REFERENCES watchlist_version (watchlist_version_id) ON DELETE RESTRICT,
    score                NUMERIC(5, 4) NOT NULL CHECK (score BETWEEN 0 AND 1),
    verdict              TEXT        NOT NULL CHECK (verdict IN ('strong_match', 'needs_review', 'no_match')),
    screened_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX screening_result_account_idx ON screening_result (account_key);
CREATE INDEX screening_result_case_idx    ON screening_result (case_id);
