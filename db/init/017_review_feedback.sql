-- Nhãn từ chuyên viên — đầu vào để hiệu chỉnh ngưỡng và huấn luyện lại.
--
-- Quyết định rà soát trước đây chỉ được ghi vào investigation.human_review
-- (jsonb, một bản ghi duy nhất, bị ghi đè mỗi lần rà soát lại) và một dòng
-- audit_log. Cả hai đều phục vụ kiểm toán, không truy vấn được theo lô, và
-- không giữ *điểm số tại thời điểm ra quyết định* — mà thiếu điểm thì cái nhãn
-- không hiệu chỉnh được cho cái gì cả.
--
-- Bảng này đóng mũi tên "Feedback / learning loop" ở mức dữ liệu. Việc tiêu thụ
-- nhãn (hiệu chỉnh ngưỡng, huấn luyện lại) là bước tiếp theo và nằm ngoài file
-- này; xem docs/handoff/detection_branch_contract.md.

CREATE TABLE IF NOT EXISTS review_feedback (
    feedback_id           TEXT PRIMARY KEY,
    investigation_id      TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    alert_id              TEXT REFERENCES alert(alert_id) ON DELETE SET NULL,
    case_id               TEXT,
    account_key           TEXT NOT NULL,

    -- Quyết định nguyên văn của chuyên viên, và nhãn đã quy đổi để mô hình dùng.
    decision              TEXT NOT NULL,
    label                 TEXT NOT NULL,
    reason                TEXT NOT NULL DEFAULT '',

    -- Ảnh chụp tại thời điểm ra quyết định. Điểm ở bảng alert có thể đổi khi
    -- nạp bản phát hành mới; nhãn phải gắn với con số mà chuyên viên đã nhìn.
    risk_score            NUMERIC(5,2),
    detector              TEXT,
    typology_code         TEXT,
    typology_was_fallback BOOLEAN,
    investigation_status  TEXT NOT NULL,

    reviewed_by           TEXT NOT NULL,
    reviewed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT review_feedback_label_check
        CHECK (label IN ('SUSPICIOUS', 'NOT_SUSPICIOUS', 'INCONCLUSIVE'))
);

-- Lấy nhãn theo lô để huấn luyện: theo thời gian, và theo nhãn.
CREATE INDEX IF NOT EXISTS review_feedback_reviewed_at_idx
    ON review_feedback (reviewed_at DESC);
CREATE INDEX IF NOT EXISTS review_feedback_label_idx
    ON review_feedback (label, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS review_feedback_alert_idx
    ON review_feedback (alert_id);
