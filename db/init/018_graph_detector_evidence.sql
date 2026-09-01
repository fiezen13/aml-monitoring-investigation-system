-- Kho bằng chứng của bộ phát hiện đồ thị.
--
-- Vì sao cần một bảng riêng thay vì ghi thẳng vào ``evidence``: cột
-- ``evidence.case_id`` là NOT NULL và trỏ tới ``aml_case``, mà vụ việc chỉ sinh
-- ra khi chuyên viên (hoặc quy trình) mở điều tra. Bộ phát hiện chạy theo lô,
-- trước lúc đó rất lâu, và không có vụ việc nào để gắn vào.
--
-- Nên chia hai tầng:
--
--   graph_detector_evidence   kho sẵn có, theo (tài khoản, mốc thời gian)
--            │
--            │  GetGraphEvidence lấy đúng phần liên quan khi điều tra
--            ▼
--   evidence (case_id)        sổ bằng chứng bất biến của vụ việc
--
-- Nhờ vậy sổ bằng chứng vẫn chỉ chứa thứ đã thực sự được dùng, còn tác tử thì
-- có cái để đọc — thay vì luôn nhận ``available: false`` như trước.

CREATE TABLE IF NOT EXISTS graph_detector_evidence (
    evidence_id      TEXT PRIMARY KEY,
    account_key      TEXT NOT NULL,
    as_of_time       TIMESTAMPTZ NOT NULL,
    pattern          TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    -- Khớp GraphEvidenceResult trong src/investigation/schemas.py.
    -- Mọi transaction_id trong payload đã được đối chiếu với bảng transaction
    -- lúc nạp; bản ghi nào có cạnh không khớp thì bị loại, không nạp một nửa.
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT graph_detector_evidence_payload_check CHECK (jsonb_typeof(payload) = 'object')
);

-- Truy vấn duy nhất mà GetGraphEvidence dùng.
CREATE INDEX IF NOT EXISTS graph_detector_evidence_account_time_idx
    ON graph_detector_evidence (account_key, as_of_time DESC);

CREATE INDEX IF NOT EXISTS graph_detector_evidence_pattern_idx
    ON graph_detector_evidence (pattern);
