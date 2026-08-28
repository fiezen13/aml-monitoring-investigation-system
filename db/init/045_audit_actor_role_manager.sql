-- 045 — nhật ký kiểm toán ghi đúng vai "Quản lý".
--
-- `audit_log.actor_role` bị CHECK vào tập giá trị của mô hình vai trò CŨ
-- (analyst/investigator/mlro/auditor/system/agent). Khi ba vai hiện hành ra đời,
-- "manager" được ghi tạm là 'investigator' để khỏi đụng ràng buộc — hậu quả là
-- quyết định PHÊ DUYỆT của quản lý hiện trong nhật ký với vai "Điều tra viên",
-- đúng thứ mà một vết kiểm toán AML không được phép nói sai: người phê duyệt và
-- người điều tra là hai vai tách biệt, tách nhiệm vụ nằm ở chính chỗ đó.
--
-- Bản ghi cũ GIỮ NGUYÊN giá trị lịch sử; chỉ nới tập giá trị cho bản ghi mới.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_actor_role_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_actor_role_check
    CHECK (actor_role IN ('analyst', 'manager', 'investigator', 'mlro', 'auditor', 'system', 'agent'));
