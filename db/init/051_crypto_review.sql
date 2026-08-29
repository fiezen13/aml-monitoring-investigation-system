-- 051 — Hàng đợi rà soát cho giao dịch tiền mã hoá.
--
-- Vì sao KHÔNG dùng `aml_case`
-- ----------------------------
-- `aml_case.subject_account_key` là NOT NULL và trỏ tới `account`: mọi vụ việc
-- phải có một tài khoản ngân hàng làm chủ thể. Bộ dữ liệu Elliptic thì đã ẩn
-- danh — chỉ có mã giao dịch và đặc trưng đồ thị, không địa chỉ ví, không khách
-- hàng, không tài khoản.
--
-- Nới ràng buộc ấy để nhét giao dịch Bitcoin vào sẽ sinh ra một vụ việc KHÔNG
-- điều tra được (chuỗi điều tra truy vấn giao dịch theo `account_key`) và KHÔNG
-- xuất được hồ sơ SAR (hồ sơ nối `account` → `customer` để dựng khối "Đối tượng
-- bị báo cáo"). Một vụ việc rỗng ruột nằm chung hàng đợi với vụ việc thật thì
-- tệ hơn là không có.
--
-- Nên đây là một hàng đợi RIÊNG, trung thực với dữ liệu đang có: chuyên viên
-- đưa giao dịch vào rà soát, ghi kết luận, chuyển cho người khác — không giả vờ
-- rằng nó là một vụ việc ngân hàng.

CREATE TABLE IF NOT EXISTS crypto_review (
    review_id       TEXT PRIMARY KEY,
    -- Không có khoá ngoại tới `bitcoin_scored_tx`: bảng ấy được nạp lại theo
    -- từng bản phát hành mô hình, và một lượt rà soát đã kết luận thì không
    -- được biến mất chỉ vì bản chấm điểm được thay.
    tx_id           TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'TiepNhan',
    risk_level      TEXT,
    illicit_prob    NUMERIC,
    assigned_to     TEXT REFERENCES app_user(user_id),
    opened_by       TEXT NOT NULL REFERENCES app_user(user_id),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Kết luận của con người. Mô hình chỉ chấm điểm; kết luận là của chuyên viên.
    conclusion      TEXT,
    conclusion_note TEXT,
    concluded_by    TEXT REFERENCES app_user(user_id),
    concluded_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crypto_review_state_check
        CHECK (state IN ('TiepNhan', 'DangRaSoat', 'KetLuan')),
    CONSTRAINT crypto_review_conclusion_check
        CHECK (conclusion IS NULL OR conclusion IN ('dang_ngo', 'khong_dang_ngo')),
    -- Đã kết luận thì phải có đủ người, thời điểm và lý do. Một kết luận không
    -- nói vì sao thì sáu tháng sau không ai dựng lại được vì sao nó được đóng.
    CONSTRAINT crypto_review_concluded_needs_reason
        CHECK (state <> 'KetLuan' OR (conclusion IS NOT NULL
                                      AND concluded_by IS NOT NULL
                                      AND concluded_at IS NOT NULL
                                      AND length(btrim(coalesce(conclusion_note, ''))) > 0))
);

-- Một giao dịch chỉ nằm trong hàng đợi một lần khi CHƯA kết luận. Đã kết luận
-- rồi thì mở lại được — và lượt mới là một bản ghi mới, giữ nguyên lượt cũ.
CREATE UNIQUE INDEX IF NOT EXISTS crypto_review_open_tx_idx
    ON crypto_review (tx_id) WHERE state <> 'KetLuan';

CREATE INDEX IF NOT EXISTS crypto_review_queue_idx
    ON crypto_review (state, opened_at DESC);
CREATE INDEX IF NOT EXISTS crypto_review_assignee_idx
    ON crypto_review (assigned_to) WHERE assigned_to IS NOT NULL;

-- Vết kiểm toán đi chung `audit_log`. Không dựng bảng nhật ký thứ hai: hai nơi
-- cùng ghi vết thì sớm muộn chúng kể hai câu chuyện khác nhau. `case_id` để
-- trống vì đây không phải vụ việc ngân hàng; mã lượt rà soát nằm trong payload.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check
    CHECK (event_type IN (
        'agent_query', 'alert_raised', 'case_state_changed', 'case_assigned',
        'submitted_for_approval', 'approved', 'rejected', 'more_info_requested',
        'file_exported', 'case_viewed', 'user_login', 'setting_changed', 'user_changed',
        'sar_updated', 'validation_run', 'investigation_started', 'investigation_completed',
        'investigation_failed', 'investigation_reviewed',
        'action_proposed', 'action_confirmed', 'action_executed',
        'action_cancelled', 'action_rejected_by_policy', 'action_expired',
        'crypto_review_opened', 'crypto_review_assigned', 'crypto_review_concluded'
    ));
