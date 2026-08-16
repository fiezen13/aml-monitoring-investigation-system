-- Kết quả kiểm tra chất lượng dữ liệu và giám sát mô hình.
--
-- Vì sao lưu sẵn thay vì tính lúc mở trang: hai màn hình này hỏi những câu phải
-- quét toàn bộ bảng ``transaction`` (6,1 triệu dòng) — "bao nhiêu giao dịch có
-- số tiền âm", "phân phối điểm dịch chuyển thế nào theo thời gian". Tính trực
-- tiếp thì mỗi lần mở trang mất hàng chục giây, và mười người mở cùng lúc thì
-- cơ sở dữ liệu chỉ còn làm mỗi việc đó.
--
-- Nên tách hai nhịp:
--
--   scripts/run_data_quality.py   chạy theo lô, quét thật, ghi kết quả xuống
--            │
--            ▼
--   data_quality_check /          hai bảng nhỏ, đọc bằng một truy vấn
--   model_monitor_metric
--
-- Đổi lại, mỗi dòng phải mang ``observed_at`` của *lần chạy*, không phải lúc
-- đọc: người xem cần biết con số này cũ bao nhiêu.

CREATE TABLE IF NOT EXISTS data_quality_check (
    check_id     TEXT PRIMARY KEY,
    dataset      TEXT        NOT NULL,
    check_name   TEXT        NOT NULL,
    -- Sáu chiều chất lượng dữ liệu quen thuộc; giữ nguyên tiếng Anh vì đây là
    -- từ vựng chuẩn của lĩnh vực, giao diện tự dịch khi hiển thị.
    dimension    TEXT        NOT NULL CHECK (dimension IN (
                     'completeness', 'validity', 'consistency',
                     'uniqueness', 'accuracy', 'timeliness')),
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    pass_rate    NUMERIC(9,8) NOT NULL CHECK (pass_rate BETWEEN 0 AND 1),
    threshold    NUMERIC(9,8) NOT NULL CHECK (threshold BETWEEN 0 AND 1),
    rows_checked BIGINT      NOT NULL CHECK (rows_checked >= 0),
    rows_failed  BIGINT      NOT NULL CHECK (rows_failed >= 0),
    status       TEXT        NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
    detail       TEXT        NOT NULL,
    CONSTRAINT data_quality_check_failed_fits CHECK (rows_failed <= rows_checked)
);

CREATE INDEX IF NOT EXISTS data_quality_check_observed_idx
    ON data_quality_check (observed_at DESC, dataset);

-- Chỉ số giám sát mô hình theo thời gian.
--
-- ``observed_at`` là mốc của *dữ liệu* được đo, không phải lúc chạy script:
-- đường trôi (drift) chỉ có nghĩa khi trục hoành là thời gian giao dịch. Một
-- lần chạy sinh ra nhiều mốc, mỗi mốc một dòng.
CREATE TABLE IF NOT EXISTS model_monitor_metric (
    release_id   TEXT        NOT NULL REFERENCES edge_model_release(release_id) ON DELETE CASCADE,
    observed_at  TIMESTAMPTZ NOT NULL,
    metric_name  TEXT        NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    -- NULL ở kỳ tham chiếu: không có gì để so nên không có điểm trôi. Ghi 0 vào
    -- đó sẽ nói dối rằng "đã đo và không trôi".
    drift_score  DOUBLE PRECISION,
    status       TEXT        NOT NULL CHECK (status IN ('healthy', 'watch', 'degraded')),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, observed_at, metric_name)
);

CREATE INDEX IF NOT EXISTS model_monitor_metric_time_idx
    ON model_monitor_metric (observed_at, metric_name);
