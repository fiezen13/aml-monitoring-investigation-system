-- Vật hóa kết quả vượt ngưỡng của release IBM đang hoạt động thành cảnh báo.
--
-- Production có đủ transaction_model_score và edge_model_release.triggered_rows
-- nhưng thiếu các dòng ALT-EDGE tương ứng. Vì 039 đã tự tạo vụ việc trước AI,
-- mỗi cảnh báo được chèn ở đây sẽ đồng thời nhận một hồ sơ aml_case 1:1. Không
-- migration nào trong file này tạo investigation hoặc đưa tác vụ vào Redis.

WITH active_release AS (
    SELECT release_id
      FROM edge_model_release
     WHERE status = 'active'
       AND dataset ILIKE '%IBM%'
     LIMIT 1
)
INSERT INTO alert (
    alert_id, account_key, transaction_id, typology_code, detector,
    risk_score, status, case_id, created_at, dataset
)
SELECT
    'ALT-EDGE-' || substr(md5(r.release_id || '|' || t.source_transaction_id), 1, 20),
    t.from_account_key,
    t.transaction_id,
    'T02',
    'ml',
    round((s.model_score * 100)::numeric, 2),
    'open',
    NULL,
    t.occurred_at,
    'ibm_hi_medium'
  FROM active_release r
  JOIN transaction_model_score s
    ON s.release_id = r.release_id AND s.triggered
  JOIN transaction t ON t.transaction_id = s.transaction_id
 WHERE t.source_transaction_id IS NOT NULL
ON CONFLICT (alert_id) DO NOTHING;

WITH active_release AS (
    SELECT release_id
      FROM edge_model_release
     WHERE status = 'active'
       AND dataset ILIKE '%IBM%'
     LIMIT 1
), triggered_alert AS (
    SELECT
        'ALT-EDGE-' || substr(md5(r.release_id || '|' || t.source_transaction_id), 1, 20) AS alert_id,
        s.model_score,
        s.threshold
      FROM active_release r
      JOIN transaction_model_score s
        ON s.release_id = r.release_id AND s.triggered
      JOIN transaction t ON t.transaction_id = s.transaction_id
     WHERE t.source_transaction_id IS NOT NULL
)
INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
SELECT
    a.alert_id,
    reason.factor_code,
    reason.factor_label,
    reason.contribution,
    reason.weight
  FROM triggered_alert a
 CROSS JOIN LATERAL (
    VALUES
      ('MODEL_SCORE', 'Điểm của mô hình phát hiện',
       round((a.model_score * 100)::numeric, 2), 1.00::numeric),
      ('THRESHOLD_MARGIN', 'Mức vượt ngưỡng cảnh báo',
       round(((a.model_score - a.threshold) * 100)::numeric, 2), 1.00::numeric),
      ('POLICY_CONTRACT', 'Giao dịch được chấm theo đồng tiền gốc',
       0.00::numeric, 0.00::numeric)
 ) reason(factor_code, factor_label, contribution, weight)
ON CONFLICT (alert_id, factor_code) DO NOTHING;

WITH active_release AS (
    SELECT release_id
      FROM edge_model_release
     WHERE status = 'active'
       AND dataset ILIKE '%IBM%'
     LIMIT 1
), triggered_alert AS (
    SELECT 'ALT-EDGE-' || substr(md5(r.release_id || '|' || t.source_transaction_id), 1, 20) AS alert_id
      FROM active_release r
      JOIN transaction_model_score s
        ON s.release_id = r.release_id AND s.triggered
      JOIN transaction t ON t.transaction_id = s.transaction_id
     WHERE t.source_transaction_id IS NOT NULL
)
INSERT INTO alert_typology_match (
    alert_id, typology_code, pattern, catalog_version,
    observed_signals, matched_required, matched_supporting,
    is_fallback, rationale
)
SELECT
    a.alert_id,
    'T02',
    'MULE_NETWORK',
    'v1',
    '[]'::jsonb,
    '[]'::jsonb,
    '[]'::jsonb,
    true,
    'Mô hình chấm ở mức giao dịch nên chưa đủ tín hiệu để kết luận nhóm hành vi; T02 chỉ là mã mặc định.'
  FROM triggered_alert a
ON CONFLICT (alert_id) DO NOTHING;
