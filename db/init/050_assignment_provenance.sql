-- 050 — Xuất xứ của một lượt phân công: giao lúc nào, ai giao, qua đường nào.
--
-- Việc phân công đã có sẵn nơi lưu: `aml_case.assigned_to` (người xử lý),
-- `due_at` (hạn), `priority` (mức ưu tiên), `case_note` (chỉ dẫn). Không dựng
-- thêm một bảng "task" song song — hai nơi cùng nói một sự thật thì sớm muộn
-- chúng lệch nhau, và câu hỏi "hồ sơ này đang ở đâu" lại có hai câu trả lời.
--
-- Thứ còn thiếu chỉ là XUẤT XỨ. Nó suy được từ `audit_log`, nhưng suy lại cho
-- mỗi dòng của một bảng hàng nghìn hồ sơ thì quá đắt để lọc và sắp xếp. Ba cột
-- dưới đây là ảnh chụp của lượt giao GẦN NHẤT; lịch sử đầy đủ vẫn nằm ở
-- `audit_log` và không bị ghi đè.

ALTER TABLE aml_case ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE aml_case ADD COLUMN IF NOT EXISTS assigned_by TEXT REFERENCES app_user(user_id);
ALTER TABLE aml_case ADD COLUMN IF NOT EXISTS assignment_source TEXT;

-- Chỉ hai nguồn vì hệ thống chỉ có hai đường tạo phân công: người dùng thao tác
-- trên màn hình, hoặc người dùng xác nhận một đề xuất của trợ lý. KHÔNG thêm
-- 'system' cho đủ bộ — chưa có luồng nào tự động giao việc, và một giá trị
-- không bao giờ xuất hiện chỉ làm người đọc tưởng nó có.
ALTER TABLE aml_case DROP CONSTRAINT IF EXISTS aml_case_assignment_source_check;
ALTER TABLE aml_case ADD CONSTRAINT aml_case_assignment_source_check
    CHECK (assignment_source IS NULL OR assignment_source IN ('manual', 'ai_copilot'));

-- Lọc theo người xử lý và sắp theo hạn là hai thao tác chính của màn Phân công.
CREATE INDEX IF NOT EXISTS aml_case_assignee_due_idx
    ON aml_case (assigned_to, due_at NULLS LAST);

-- Hàng đợi "chưa phân công", sắp theo rủi ro giảm dần.
CREATE INDEX IF NOT EXISTS aml_case_unassigned_risk_idx
    ON aml_case (risk_score DESC) WHERE assigned_to IS NULL;

-- Vá ngược cho các lượt giao ĐÃ có: lấy mốc thời gian, người giao và nguồn từ
-- vết kiểm toán gần nhất. Không có vết thì để trống — thà thiếu còn hơn bịa một
-- ngày giao không có thật.
UPDATE aml_case c
   SET assigned_at = l.occurred_at,
       assigned_by = CASE WHEN u.user_id IS NOT NULL THEN l.actor END,
       assignment_source = CASE
           WHEN l.payload->>'source' = 'approval_copilot' THEN 'ai_copilot'
           ELSE 'manual'
       END
  FROM (
        SELECT DISTINCT ON (case_id) case_id, actor, occurred_at, payload
          FROM audit_log
         WHERE event_type = 'case_assigned'
         ORDER BY case_id, occurred_at DESC
       ) l
  LEFT JOIN app_user u ON u.user_id = l.actor
 WHERE c.case_id = l.case_id
   AND c.assigned_to IS NOT NULL
   AND c.assigned_at IS NULL;
