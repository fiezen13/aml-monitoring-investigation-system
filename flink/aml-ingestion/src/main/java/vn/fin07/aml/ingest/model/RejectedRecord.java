package vn.fin07.aml.ingest.model;

import java.io.Serializable;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

/**
 * Một sự kiện không dùng được, kèm lý do và đủ thông tin để truy ngược.
 *
 * <p>Không sự kiện nào bị bỏ đi trong im lặng. Sự kiện hỏng đi ra một nhánh
 * riêng (side output) rồi xuống HDFS ở vùng {@code rejected}, mang theo
 * nguyên văn payload đã nhận. Một luồng dữ liệu chỉ đáng tin khi số bản ghi
 * vào bằng số hợp lệ cộng số bị từ chối, và điều đó chỉ đúng khi phần bị từ
 * chối được ghi lại chứ không bị nuốt.
 */
public class RejectedRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd");

    public String errorType;
    public String errorMessage;
    public String rawPayload;
    public String kafkaTopic;
    public int kafkaPartition;
    public long kafkaOffset;
    public long kafkaTimestamp;
    public String transactionId;
    public String sourceFile;
    public long sourceLineNumber;
    public String eventDate;
    public String rejectedAt;
    public String stage;

    public RejectedRecord() {
        // Flink cần constructor rỗng.
    }

    public static RejectedRecord of(
            String errorType,
            String errorMessage,
            String rawPayload,
            String topic,
            int partition,
            long offset,
            long timestamp) {
        RejectedRecord record = new RejectedRecord();
        record.errorType = errorType;
        record.errorMessage = errorMessage;
        record.rawPayload = rawPayload;
        record.kafkaTopic = topic;
        record.kafkaPartition = partition;
        record.kafkaOffset = offset;
        record.kafkaTimestamp = timestamp;
        record.stage = "flink-ingestion";
        Instant now = Instant.now();
        record.rejectedAt = now.toString();
        // Phân vùng theo ngày *xử lý*, không theo event time: sự kiện bị từ
        // chối thường là sự kiện không có event time đọc được.
        record.eventDate = DATE.format(now.atZone(ZoneOffset.UTC));
        record.transactionId = "";
        record.sourceFile = "";
        record.sourceLineNumber = -1L;
        return record;
    }

    /** Bổ sung thông tin truy vết khi đọc được một phần payload. */
    public RejectedRecord withSource(String transactionId, String sourceFile, long sourceLineNumber) {
        this.transactionId = transactionId == null ? "" : transactionId;
        this.sourceFile = sourceFile == null ? "" : sourceFile;
        this.sourceLineNumber = sourceLineNumber;
        return this;
    }

    @Override
    public String toString() {
        return "RejectedRecord{" + errorType + " " + kafkaTopic + "-" + kafkaPartition + "@" + kafkaOffset + "}";
    }
}
