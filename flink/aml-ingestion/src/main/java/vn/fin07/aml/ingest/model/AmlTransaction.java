package vn.fin07.aml.ingest.model;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Objects;

/**
 * Một giao dịch đã chuẩn hoá, tương ứng một sự kiện của
 * {@code aml.transactions.raw.v1}.
 *
 * <p>Đây là kiểu dữ liệu đi xuyên suốt job. Không có {@code Map<String,
 * Object>} nào trong đường đi: một map thì trình biên dịch không kiểm tra
 * được gì, và mọi lỗi gõ nhầm tên trường sẽ chỉ lộ ra lúc chạy, trên dữ liệu
 * thật, ở tầng lưu trữ.
 *
 * <p>Định danh ngân hàng và tài khoản là {@code String}, có chủ ý và không
 * được đổi: mã {@code 015768} chuyển sang số rồi in lại thành {@code 15768},
 * tức là một ngân hàng khác.
 *
 * <p>Số tiền giữ ở {@link BigDecimal} trong suốt phần xử lý, vì đây là dữ
 * liệu tài chính và sai số dấu phẩy động là thứ tích luỹ âm thầm. Chỉ ở
 * bước ghi Parquet mới đổi sang {@code double} — xem ghi chú trong
 * {@code AvroSchemas}.
 *
 * <p>Lớp này là POJO theo đúng nghĩa Flink cần (constructor rỗng, trường
 * public) để dùng được bộ tuần tự hoá POJO thay vì Kryo.
 */
public class AmlTransaction implements Serializable {

    private static final long serialVersionUID = 1L;

    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter HOUR = DateTimeFormatter.ofPattern("HH");

    // ---- Trường của lược đồ chuẩn hoá v1.0 ----
    public String transactionId;
    public String eventTime;
    public long eventTimeEpochMs;
    public String fromBank;
    public String fromAccount;
    public String toBank;
    public String toAccount;
    public BigDecimal amountReceived;
    public String receivingCurrency;
    public BigDecimal amountPaid;
    public String paymentCurrency;
    public String paymentFormat;
    public int isLaundering;
    public String sourceDataset;
    public String sourceFile;
    public long sourceLineNumber;
    public String ingestedAt;
    public String schemaVersion;

    // ---- Trường kỹ thuật do job này thêm vào ----
    // Chỉ phục vụ việc nạp và phân vùng dữ liệu. Không có trường phái sinh
    // nào mang ý nghĩa nghiệp vụ AML ở đây.
    public String flinkProcessedAt;
    public String eventDate;
    public String eventHour;
    public int kafkaPartition;
    public long kafkaOffset;

    public AmlTransaction() {
        // Flink cần constructor rỗng để dùng PojoSerializer.
    }

    /** Ghi lại vị trí của sự kiện trong Kafka, để truy vết được về nguồn. */
    public void assignKafkaMetadata(int partition, long offset) {
        this.kafkaPartition = partition;
        this.kafkaOffset = offset;
    }

    /**
     * Tính các trường phân vùng từ event time.
     *
     * <p>Gọi sau khi kiểm tra hợp lệ, vì hàm này tin rằng
     * {@code eventTimeEpochMs} nằm trong khoảng hợp lý.
     *
     * <p>Ngày và giờ luôn được quy về UTC. Nếu để múi giờ của máy chạy quyết
     * định thì cùng một sự kiện sẽ rơi vào hai thư mục khác nhau tuỳ theo
     * TaskManager nào xử lý nó, và phân vùng trên HDFS sẽ không tái lập được.
     */
    public void deriveTimeFields() {
        Instant instant = Instant.ofEpochMilli(eventTimeEpochMs);
        this.eventDate = DATE.format(instant.atZone(ZoneOffset.UTC));
        this.eventHour = HOUR.format(instant.atZone(ZoneOffset.UTC));
        this.flinkProcessedAt = Instant.now().toString();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof AmlTransaction)) {
            return false;
        }
        AmlTransaction that = (AmlTransaction) other;
        return Objects.equals(transactionId, that.transactionId)
                && eventTimeEpochMs == that.eventTimeEpochMs
                && Objects.equals(sourceFile, that.sourceFile)
                && sourceLineNumber == that.sourceLineNumber;
    }

    @Override
    public int hashCode() {
        return Objects.hash(transactionId, eventTimeEpochMs, sourceFile, sourceLineNumber);
    }

    @Override
    public String toString() {
        return "AmlTransaction{" + transactionId + " " + eventTime + " " + fromBank + ":" + fromAccount + " -> "
                + toBank + ":" + toAccount + " " + amountPaid + " " + paymentCurrency + "}";
    }
}
