-- Thêm sự kiện "vòng lặp kiểm chứng giậm chân" vào nhật ký điều tra.
--
-- Quy trình dừng sớm khi một vòng phản biện nêu lại ĐÚNG bộ vấn đề của vòng
-- trước: đo trên 16 phiên chạy nhiều vòng, 11 phiên giảm dần số vấn đề về 0
-- (vòng lặp có tác dụng thật) nhưng 2 phiên lặp nguyên văn cùng bộ khiếu nại
-- qua cả ba vòng. Với chúng, vòng sau đọc đúng bằng chứng cũ, viết lại theo
-- đúng cách cũ, và trượt vì đúng lý do cũ — chỉ tốn thêm lượt gọi mô hình.
--
-- Phải là sự kiện RIÊNG, không gộp vào VALIDATION_FAIL: hai thứ này đòi hai
-- cách xử lý khác hẳn nhau. Cạn ngân sách thì chạy lại còn có cơ hội; giậm chân
-- thì chạy lại cho ra đúng kết quả cũ, và việc cần làm là chuyên viên đọc bằng
-- chứng rồi quyết định. Giao diện đọc chính tín hiệu này để hạ nút "Chạy lại"
-- xuống thứ yếu thay vì mời người dùng bấm một nút vô ích.
--
-- Không viết lại dữ liệu cũ: nhật ký điều tra là bản ghi bất biến phục vụ
-- kiểm toán.

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
        'VALIDATION_STALLED',
        'CRITIC_OBJECTION_REFUTED',
        'INVESTIGATION_COMPLETED',
        'INVESTIGATION_FAILED',
        'HUMAN_REVIEW_REQUIRED',
        'GEMINI_REQUEST',
        'GEMINI_RESPONSE',
        'GEMINI_ERROR',
        'INVALID_TOOL_REQUEST'
    ));
