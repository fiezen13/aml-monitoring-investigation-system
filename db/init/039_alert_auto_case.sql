-- Mỗi cảnh báo nghiệp vụ chưa đóng phải có sẵn một vụ việc để chuyên viên xử lý.
--
-- Giao diện không còn một hàng đợi Cảnh báo riêng. Vì vậy bắt người dùng mở từng
-- cảnh báo rồi bấm "Bắt đầu điều tra" chỉ để tạo aml_case là một bước thừa, đồng
-- thời trộn việc tạo hồ sơ nhẹ với việc gọi AI tốn tài nguyên. Migration này:
--   1. backfill các cảnh báo đang mở chưa có vụ việc;
--   2. tự tạo vụ việc cho mọi cảnh báo mới;
--   3. KHÔNG tạo investigation và KHÔNG đưa tác vụ AI vào hàng đợi.

CREATE OR REPLACE FUNCTION create_case_for_new_alert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    generated_case_id TEXT;
BEGIN
    IF NEW.case_id IS NOT NULL OR NEW.status = 'closed' THEN
        RETURN NEW;
    END IF;

    generated_case_id := 'CASE-AUTO-' || substr(md5(NEW.alert_id), 1, 24);

    INSERT INTO aml_case (
        case_id, subject_account_key, title, state, risk_score, priority,
        created_at, updated_at
    )
    VALUES (
        generated_case_id,
        NEW.account_key,
        'Rà soát cảnh báo ' || NEW.alert_id,
        'TiepNhanCanhBao',
        NEW.risk_score,
        CASE
            WHEN NEW.risk_score >= 80 THEN 'critical'
            WHEN NEW.risk_score >= 60 THEN 'high'
            WHEN NEW.risk_score >= 40 THEN 'medium'
            ELSE 'low'
        END,
        NEW.created_at,
        NEW.created_at
    )
    ON CONFLICT (case_id) DO NOTHING;

    NEW.case_id := generated_case_id;
    NEW.status := 'grouped';
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS alert_auto_case_before_insert ON alert;
CREATE TRIGGER alert_auto_case_before_insert
BEFORE INSERT ON alert
FOR EACH ROW
EXECUTE FUNCTION create_case_for_new_alert();

-- Dữ liệu đã tồn tại: tạo hồ sơ trước rồi mới gắn cảnh báo để giữ toàn vẹn FK.
INSERT INTO aml_case (
    case_id, subject_account_key, title, state, risk_score, priority,
    created_at, updated_at
)
SELECT
    'CASE-AUTO-' || substr(md5(a.alert_id), 1, 24),
    a.account_key,
    'Rà soát cảnh báo ' || a.alert_id,
    'TiepNhanCanhBao',
    a.risk_score,
    CASE
        WHEN a.risk_score >= 80 THEN 'critical'
        WHEN a.risk_score >= 60 THEN 'high'
        WHEN a.risk_score >= 40 THEN 'medium'
        ELSE 'low'
    END,
    a.created_at,
    a.created_at
FROM alert a
WHERE a.status <> 'closed'
  AND a.case_id IS NULL
ON CONFLICT (case_id) DO NOTHING;

UPDATE alert a
   SET case_id = 'CASE-AUTO-' || substr(md5(a.alert_id), 1, 24),
       status = 'grouped'
 WHERE a.status <> 'closed'
   AND a.case_id IS NULL;

COMMENT ON FUNCTION create_case_for_new_alert() IS
    'Tự tạo hồ sơ vụ việc 1:1 cho cảnh báo mới; không khởi chạy quy trình AI.';
