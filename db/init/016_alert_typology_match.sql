-- Dấu vết ánh xạ nhóm hành vi cho từng cảnh báo.
--
-- Cột alert.typology_code là NOT NULL nên luôn phải có một mã. Trước đây cả ba
-- nơi sinh cảnh báo đều đóng dấu cứng 'T02', và không có chỗ nào phân biệt được
-- "đã chứng minh bằng tín hiệu" với "điền cho đủ cột". Tác tử phản biện vì thế
-- liên tục phản đối đúng: cảnh báo nói T02 nhưng không có tín hiệu network_flow
-- nào chứng minh.
--
-- Bảng này giữ phần còn thiếu: tín hiệu nào đã quan sát được, tín hiệu bắt buộc
-- nào đã khớp, và quan trọng nhất — mã này là kết luận hay chỉ là mặc định.

CREATE TABLE IF NOT EXISTS alert_typology_match (
    alert_id           TEXT PRIMARY KEY REFERENCES alert(alert_id) ON DELETE CASCADE,
    typology_code      TEXT NOT NULL,
    pattern            TEXT NOT NULL,
    catalog_version    TEXT NOT NULL,
    observed_signals   JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_required   JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_supporting JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- true = không tín hiệu nào đủ điều kiện, mã là giá trị mặc định.
    is_fallback        BOOLEAN NOT NULL,
    rationale          TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT alert_typology_match_code_check CHECK (typology_code ~ '^T(0[1-9]|10)$'),
    CONSTRAINT alert_typology_match_signals_check CHECK (jsonb_typeof(observed_signals) = 'array'),
    CONSTRAINT alert_typology_match_required_check CHECK (jsonb_typeof(matched_required) = 'array'),
    CONSTRAINT alert_typology_match_supporting_check CHECK (jsonb_typeof(matched_supporting) = 'array')
);

-- Truy vấn hay dùng nhất: "còn bao nhiêu cảnh báo đang mang nhóm hành vi mặc
-- định" — tức là phần bề mặt chưa được bộ phát hiện nào chứng minh.
CREATE INDEX IF NOT EXISTS alert_typology_match_fallback_idx
    ON alert_typology_match (is_fallback, typology_code);
