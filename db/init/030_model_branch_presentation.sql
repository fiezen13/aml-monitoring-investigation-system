-- 030 · Sửa cách TRÌNH BÀY các nhánh mô hình (dữ liệu edge_model_release).
--
-- Mang các chỉnh sửa vốn làm tay ở môi trường dev sang mọi môi trường qua
-- scripts/migrate.py. Cố ý:
--   • IDEMPOTENT: chạy lại nhiều lần vẫn cho cùng kết quả (WHERE chỉ khớp trạng
--     thái cũ; đã đúng thì no-op).
--   • PORTABLE: khoá theo dataset/model_kind, KHÔNG theo release_id cụ thể — id
--     sinh theo môi trường nên hardcode sẽ trượt trên production.
-- migrate.py bọc mỗi file trong một transaction rồi commit, nên KHÔNG tự mở
-- BEGIN/COMMIT ở đây.

-- 1) SAML-D (luật địa lý): bỏ nhãn "giao dịch xuyên biên giới".
UPDATE edge_model_release
   SET benchmark = benchmark || jsonb_build_object(
       'region_label', 'SAML-D · luật địa lý',
       'region_description',
       'Bộ luật địa lý trên bộ SAML-D: xếp hạng cảnh báo theo hành lang quốc gia rủi ro. Đo trên đúng vùng luật này áp dụng.')
 WHERE benchmark->>'model_kind' = 'geo_rule_ranker'
   AND benchmark->>'region_label' = 'Giao dịch xuyên biên giới';

-- 2) Bỏ mọi vết "xuyên biên giới" còn lại trong ghi chú/mô tả của các nhánh
--    (SAML-D đồ thị, ghi chú so sánh của IBM). Thay bằng "hành lang quốc gia rủi ro".
UPDATE edge_model_release
   SET benchmark = jsonb_set(benchmark, '{region_description}',
       to_jsonb(replace(benchmark->>'region_description', 'có yếu tố xuyên biên giới', 'trên bộ SAML-D')))
 WHERE benchmark ? 'region_description'
   AND benchmark->>'region_description' LIKE '%có yếu tố xuyên biên giới%';

UPDATE edge_model_release
   SET benchmark = jsonb_set(benchmark, '{not_comparable_note}',
       to_jsonb(replace(benchmark->>'not_comparable_note', 'xuyên biên giới', 'hành lang quốc gia rủi ro')))
 WHERE benchmark ? 'not_comparable_note'
   AND benchmark->>'not_comparable_note' LIKE '%xuyên biên giới%';

-- 3) Xoá release Elliptic++ cũ (dataset đã gỡ khỏi repo) — chỉ khi không còn
--    bảng nào tham chiếu tới nó.
DELETE FROM edge_model_release r
 WHERE r.dataset = 'Elliptic++'
   AND NOT EXISTS (SELECT 1 FROM transaction_model_score s WHERE s.release_id = r.release_id)
   AND NOT EXISTS (SELECT 1 FROM bitcoin_scored_tx b WHERE b.release_id = r.release_id);

-- 4) Bổ sung trường thẻ nhánh cho release Elliptic gốc để nó hiện đúng MỘT thẻ
--    Bitcoin ở /fc/model-branches (thay cho thẻ Elliptic++ vừa xoá).
UPDATE edge_model_release
   SET benchmark = benchmark || jsonb_build_object(
       'model_kind', 'random_forest_classifier',
       'region_label', 'Giao dịch Bitcoin',
       'region_description',
       'Đo trên tập test theo thời gian của Elliptic gốc (các bước thời gian muộn nhất). Random Forest chấm từng giao dịch; KHÔNG leakage-free (DFRWS 2026).')
 WHERE dataset = 'Elliptic (original)'
   AND NOT (benchmark ? 'model_kind');

-- 5) Nhánh Bitcoin phục vụ TRỰC TIẾP qua bảng bitcoin_scored_tx, không qua
--    active-join. Nếu nó đang chiếm slot 'active' (bug lần migrate trước), trả về
--    'reference' và khôi phục nhánh IBM MEGA-PNA làm 'active' — nếu không, mọi
--    phép nối transaction_model_score WHERE status='active' sẽ trượt. Hai bước
--    theo đúng thứ tự để không vi phạm ràng buộc một-active; môi trường không
--    dính bug thì cả hai là no-op.
UPDATE edge_model_release
   SET status = 'reference', activated_at = NULL
 WHERE dataset = 'Elliptic (original)' AND status = 'active';

UPDATE edge_model_release
   SET status = 'active', activated_at = now()
 WHERE release_id = (
         SELECT release_id FROM edge_model_release
          WHERE dataset LIKE '%MEGA-PNA%' ORDER BY trained_at DESC LIMIT 1)
   AND NOT EXISTS (SELECT 1 FROM edge_model_release WHERE status = 'active');
