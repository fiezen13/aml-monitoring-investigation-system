-- Tách sự kiện "bác bỏ khiếu nại của tác tử phản biện" ra khỏi VALIDATION_PASS.
--
-- Trước đây khi bộ phản biện tất định bác một khiếu nại sai của Gemini, nhật ký
-- ghi VALIDATION_PASS. Dòng thời gian vì thế đọc thành PASS rồi lại FAIL trong
-- cùng một vòng lặp, trông như hệ thống tự mâu thuẫn — trong khi kết quả kiểm
-- chứng thật sự của vòng đó là FAIL. Đây là hai sự kiện khác nhau và phải mang
-- hai tên khác nhau.
--
-- Không viết lại dữ liệu cũ: các dòng VALIDATION_PASS đã ghi vẫn giữ nguyên vì
-- nhật ký điều tra là bản ghi bất biến phục vụ kiểm toán.

ALTER TABLE investigation_trace
    DROP CONSTRAINT IF EXISTS investigation_trace_event_type_check;

ALTER TABLE investigation_trace
    ADD CONSTRAINT investigation_trace_event_type_check
    CHECK (event_type IN (
        'INVESTIGATION_STARTED',
        'AGENT_DECISION',
        'TOOL_CALL',
        'TOOL_RESULT',
        'EVIDENCE_ADDED',
        'EXPLANATION_GENERATED',
        'VALIDATION_PASS',
        'VALIDATION_FAIL',
        'CRITIC_OBJECTION_REFUTED',
        'INVESTIGATION_COMPLETED',
        'INVESTIGATION_FAILED',
        'HUMAN_REVIEW_REQUIRED',
        'GEMINI_REQUEST',
        'GEMINI_RESPONSE',
        'GEMINI_ERROR',
        'INVALID_TOOL_REQUEST'
    ));
