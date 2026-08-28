-- 046 — giao việc vụ việc.
--
-- `aml_case.assigned_to` có từ đầu nhưng KHÔNG có luồng nào ghi vào nó: toàn bộ
-- 14.267 vụ đều NULL, cột "Phụ trách" luôn là "Chưa giao", và bộ lọc "vụ của
-- tôi" luôn rỗng. Thêm sự kiện kiểm toán cho thao tác giao/nhận việc để mỗi lần
-- đổi người phụ trách đều có vết.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check
    CHECK (event_type IN (
        'agent_query', 'alert_raised', 'case_state_changed', 'case_assigned',
        'submitted_for_approval', 'approved', 'rejected', 'more_info_requested',
        'file_exported', 'case_viewed', 'user_login', 'setting_changed', 'user_changed',
        'sar_updated', 'validation_run', 'investigation_started', 'investigation_completed',
        'investigation_failed', 'investigation_reviewed'
    ));

CREATE INDEX IF NOT EXISTS idx_aml_case_assigned ON aml_case (assigned_to) WHERE assigned_to IS NOT NULL;
