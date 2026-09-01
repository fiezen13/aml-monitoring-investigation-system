-- Index cho các cột khoá ngoại đang thiếu.
--
-- PostgreSQL tự tạo index cho khoá chính, nhưng KHÔNG tạo cho phía tham chiếu
-- của khoá ngoại. Thiếu index đó thì mỗi lần xoá một dòng cha, cơ sở dữ liệu
-- phải quét toàn bộ bảng con để kiểm ràng buộc.
--
-- Đo được trên chính repo này: xoá 19.704 cảnh báo của nhánh rule treo hơn ba
-- phút rồi phải huỷ, vì ``detection_result.alert_id`` (ON DELETE SET NULL)
-- không có index và bảng đó có 200.944 dòng — tức khoảng bốn tỷ lượt duyệt
-- dòng. Với dữ liệu thật lớn hơn, thao tác này sẽ không bao giờ xong.
--
-- Các cột dưới đây đều là phía tham chiếu của một khoá ngoại và đều nằm trên
-- đường xoá hoặc đường tra cứu nóng.

CREATE INDEX IF NOT EXISTS detection_result_alert_idx
    ON detection_result (alert_id);

CREATE INDEX IF NOT EXISTS detection_result_snapshot_idx
    ON detection_result (snapshot_id);

CREATE INDEX IF NOT EXISTS detection_result_batch_idx
    ON detection_result (batch_id);

-- investigation_evidence và sar_statement_evidence tham chiếu evidence; bảng
-- evidence là append-only nên không có đường xoá, nhưng hai index này phục vụ
-- truy vấn "bằng chứng này đã được dùng ở đâu".
CREATE INDEX IF NOT EXISTS investigation_evidence_evidence_idx
    ON investigation_evidence (evidence_id);
