-- 049 — Trợ lý điều phối cho Quản lý: hành động phải qua hai nhịp ĐỀ XUẤT → XÁC NHẬN.
--
-- Trợ lý AI trên trang Phê duyệt trước nay chỉ hỏi–đáp. Khi cho nó điều phối
-- công việc, câu hỏi không còn là "trả lời có đúng không" mà là "ai chịu trách
-- nhiệm cho thay đổi này". Nên mô hình KHÔNG bao giờ được ghi thẳng: nó chỉ
-- soạn một ĐỀ XUẤT, người thật bấm xác nhận, rồi máy chủ mới thực thi bằng mã
-- tất định.
--
-- Bảng `copilot_action` là chốt giữa hai nhịp đó. Nó giữ NGUYÊN VĂN tham số
-- phía máy chủ: lúc xác nhận, máy chủ đọc lại từ đây chứ không đọc lại câu
-- tiếng Việt của người dùng và cũng không tin phần thân yêu cầu do giao diện
-- gửi lên. `payload_hash` để phát hiện sửa trộm.

CREATE TABLE IF NOT EXISTS copilot_action (
    action_id       TEXT PRIMARY KEY,
    action_type     TEXT NOT NULL,
    -- Tham số BẤT BIẾN của đề xuất. Nguồn sự thật duy nhất khi thực thi.
    payload         JSONB NOT NULL,
    payload_hash    TEXT NOT NULL,
    requested_by    TEXT NOT NULL REFERENCES app_user(user_id),
    requested_role  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'proposed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Đề xuất hết hạn: dữ liệu đổi sau vài phút thì tham số đã cũ, xác nhận
    -- muộn là áp một quyết định lên tình trạng khác với lúc nó được cân nhắc.
    expires_at      TIMESTAMPTZ NOT NULL,
    executed_at     TIMESTAMPTZ,
    result          JSONB,
    CONSTRAINT copilot_action_status_check
        CHECK (status IN ('proposed', 'executed', 'cancelled', 'expired', 'rejected')),
    CONSTRAINT copilot_action_type_check
        CHECK (action_type IN ('ASSIGN_TASK', 'REASSIGN_TASK', 'UPDATE_DEADLINE',
                               'UPDATE_PRIORITY', 'SEND_REMINDER', 'ADD_INSTRUCTION'))
);

CREATE INDEX IF NOT EXISTS copilot_action_open_idx
    ON copilot_action (requested_by, status) WHERE status = 'proposed';

-- Hạn xử lý của vụ việc. Chưa có cột nào cho việc này nên "deadline" trước đây
-- không tồn tại ngoài lời nói.
ALTER TABLE aml_case ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS aml_case_due_idx ON aml_case (due_at)
    WHERE due_at IS NOT NULL;

-- Chỉ dẫn và lời nhắc Quản lý gửi cho Chuyên viên. Tách khỏi `audit_log` vì
-- đây là nội dung để ĐỌC trong lúc làm việc, còn audit_log là vết bất biến.
CREATE TABLE IF NOT EXISTS case_note (
    note_id     BIGSERIAL PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES aml_case(case_id),
    kind        TEXT NOT NULL,
    body        TEXT NOT NULL,
    author      TEXT NOT NULL REFERENCES app_user(user_id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT case_note_kind_check CHECK (kind IN ('instruction', 'reminder'))
);

CREATE INDEX IF NOT EXISTS case_note_case_idx ON case_note (case_id, created_at DESC);

-- Vết kiểm toán cho vòng đời đề xuất. Sáu mốc, đủ để dựng lại "ai đề xuất gì,
-- ai chấp thuận, máy chủ làm gì" mà không cần đọc log ứng dụng.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check
    CHECK (event_type IN (
        'agent_query', 'alert_raised', 'case_state_changed', 'case_assigned',
        'submitted_for_approval', 'approved', 'rejected', 'more_info_requested',
        'file_exported', 'case_viewed', 'user_login', 'setting_changed', 'user_changed',
        'sar_updated', 'validation_run', 'investigation_started', 'investigation_completed',
        'investigation_failed', 'investigation_reviewed',
        'action_proposed', 'action_confirmed', 'action_executed',
        'action_cancelled', 'action_rejected_by_policy', 'action_expired'
    ));
