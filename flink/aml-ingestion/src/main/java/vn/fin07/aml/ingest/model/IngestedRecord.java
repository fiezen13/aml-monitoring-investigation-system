package vn.fin07.aml.ingest.model;

import java.io.Serializable;

/**
 * Kết quả đọc một message Kafka: hoặc một giao dịch dùng được, hoặc một bản
 * ghi bị từ chối kèm lý do.
 *
 * <p>Đúng một trong hai trường khác null. Kiểu này tồn tại để lỗi giải mã
 * **đi tiếp** trong luồng thay vì làm job chết hoặc bị nuốt: một
 * {@code DeserializationSchema} trả về {@code null} khi gặp lỗi là cách phổ
 * biến nhất để đánh mất dữ liệu mà không ai biết.
 */
public class IngestedRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    public AmlTransaction transaction;
    public RejectedRecord rejected;

    public IngestedRecord() {
        // Flink cần constructor rỗng.
    }

    public static IngestedRecord valid(AmlTransaction transaction) {
        IngestedRecord record = new IngestedRecord();
        record.transaction = transaction;
        return record;
    }

    public static IngestedRecord invalid(RejectedRecord rejected) {
        IngestedRecord record = new IngestedRecord();
        record.rejected = rejected;
        return record;
    }

    public boolean isValid() {
        return transaction != null;
    }
}
