-- 038 · Nối streaming vào VỤ VIỆC THẬT (aml_case) — sửa hướng Pha 4.
--
-- Bỏ stream_case/stream_alert (037): vụ việc/cảnh báo streaming phải là THẬT trong
-- alert + aml_case để chuyên viên mở, điều tra, xuất SAR như mọi vụ khác (máy trạng
-- thái 12 bước). Chỉ giữ hai bảng SỔ nhẹ để bồi tụ idempotent + union-find:
--   * stream_alert_link: cạnh streaming nào đã thành cảnh báo (khỏi tạo trùng),
--   * stream_case_membership: tài khoản (khoá ISO) đang thuộc vụ nào (để gộp cạnh).

DROP TABLE IF EXISTS stream_alert;
DROP TABLE IF EXISTS stream_case_account;
DROP TABLE IF EXISTS stream_case;

CREATE TABLE IF NOT EXISTS stream_alert_link (
    stream_txn_id BIGINT PRIMARY KEY REFERENCES stream_transaction (stream_txn_id) ON DELETE CASCADE,
    alert_id      TEXT NOT NULL,
    case_id       TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chỉ số union-find: tài khoản (đã chuẩn hoá ISO) → vụ việc aml_case đang chứa nó.
CREATE TABLE IF NOT EXISTS stream_case_membership (
    account_key TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS stream_case_membership_case_idx ON stream_case_membership (case_id);
