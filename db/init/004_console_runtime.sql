-- Dữ liệu vận hành của console: người dùng/xác thực và cấu hình có thể chỉnh.
-- Các màn hình này trước đây lấy hằng số TypeScript nên không tham gia luồng E2E.

CREATE TABLE app_user (
    user_id       TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL CHECK (role IN ('compliance_officer', 'mlro', 'auditor', 'admin', 'analyst')),
    role_label    TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active        BOOLEAN NOT NULL DEFAULT true,
    last_login    TIMESTAMPTZ
);

CREATE TABLE app_session (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX app_session_user_idx ON app_session(user_id);
CREATE INDEX app_session_expiry_idx ON app_session(expires_at);

CREATE TABLE system_setting (
    code       TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    value      TEXT NOT NULL,
    unit       TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL,
    updated_by TEXT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_user (user_id, name, email, role, role_label, password_salt, password_hash, active) VALUES
('U-001', 'Nguyễn Quang Hưng', 'hung.nq@velrix.vn', 'compliance_officer', 'Compliance Officer', '66696e30372d757365722d303031', 'a92eb7ec038b1ad4d3a3bfed5b11baaeb9b4fc0f1b1431d4429a963afcfcd61e', true),
('U-002', 'Trần Hoàng Quân', 'quan.th@velrix.vn', 'compliance_officer', 'Compliance Officer', '66696e30372d757365722d303032', 'b4c27bd20cc64b9132ab20d4209d05bf79ec5f715b26edc389f4afc74d63a4ab', true),
('U-003', 'Đàm Minh Tuấn', 'tuan.dm@velrix.vn', 'mlro', 'MLRO', '66696e30372d757365722d303033', '0cff822800d5b118defee5462e00f62c88fca7a4f16c1f68196ef6d9ed62d627', true),
('U-004', 'Lê Minh Khiêm', 'khiem.lm@velrix.vn', 'auditor', 'Auditor', '66696e30372d757365722d303034', '0a29df626256ca7d5fc08c68f77b30e2e046f7b2c1d07d091f6751704179ae77', true),
('U-005', 'Đinh Huy Mạnh', 'manh.dh@velrix.vn', 'admin', 'Administrator', '66696e30372d757365722d303035', '386c9edf90593ec0b62bf6289c91035057a51011750d30c819071f8e9fa6b22c', true),
('U-006', 'Lê Anh Tuấn', 'tuan.la@velrix.vn', 'analyst', 'Senior Analyst', '66696e30372d757365722d303036', '855332943348d781d35c18520a1677f199bdfdfe631bd92330d3e0d47518fc34', true),
('U-007', 'Phạm Văn Vĩnh', 'vinh.pv@velrix.vn', 'analyst', 'Analyst', '66696e30372d757365722d303037', '869ad05e155634818f13c196a4b23dad6db7a97a16d8918d3efc1b42bfc2e8b4', false);

INSERT INTO system_setting (code, label, value, unit, source) VALUES
('T01-AMT', 'Ngưỡng báo cáo giao dịch tiền mặt', '200000000', 'VNĐ', 'Quy định nội bộ QD3'),
('T01-VEL', 'Số giao dịch tối đa / 2 giờ trước khi cảnh báo', '10', 'giao dịch', 'Risk Engine · rule'),
('SCR-TH', 'Ngưỡng điểm đối chiếu danh sách', '0.75', 'điểm', 'Screening Service'),
('SLA-ALERT', 'SLA xử lý cảnh báo rủi ro cao', '4', 'giờ', 'Quy định nội bộ QD6'),
('NOTIFY-INTERNAL', 'Gửi thông báo rủi ro cao tới đội Compliance', 'true', 'boolean', 'Internal Notification');

-- Mở rộng từ vựng audit cho thao tác console. Giữ toàn bộ giá trị cũ.
ALTER TABLE audit_log DROP CONSTRAINT audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check CHECK (event_type IN (
    'agent_query', 'alert_raised', 'case_state_changed', 'submitted_for_approval',
    'approved', 'rejected', 'more_info_requested', 'file_exported', 'case_viewed',
    'user_login', 'setting_changed', 'user_changed', 'sar_updated', 'validation_run'
));
