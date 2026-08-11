package vn.fin07.aml.ingest.sink;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.Serializable;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.model.RejectedRecord;

/**
 * Chuyển bản ghi sang JSON Lines để ghi xuống HDFS.
 *
 * <p>Dùng cho hai chỗ: định dạng đầu ra {@code json} (phương án thay thế
 * Parquet), và vùng dữ liệu bị từ chối — vùng này luôn là JSON Lines vì bản
 * ghi bị từ chối vốn không có lược đồ cố định, và đọc bằng mắt là việc sẽ
 * làm nhiều nhất với nó.
 *
 * <p>Tên trường viết snake_case, khớp hợp đồng dữ liệu và khớp cột Parquet,
 * để đổi định dạng đầu ra không kéo theo phải đổi truy vấn.
 */
public final class JsonEncoders implements Serializable {

    private static final long serialVersionUID = 1L;

    private transient ObjectMapper mapper;

    private ObjectMapper mapper() {
        if (mapper == null) {
            mapper = new ObjectMapper();
        }
        return mapper;
    }

    public String transactionToJson(AmlTransaction tx) {
        ObjectNode node = mapper().createObjectNode();
        node.put("transaction_id", tx.transactionId);
        node.put("event_time", tx.eventTime);
        node.put("event_time_epoch_ms", tx.eventTimeEpochMs);
        node.put("from_bank", tx.fromBank);
        node.put("from_account", tx.fromAccount);
        node.put("to_bank", tx.toBank);
        node.put("to_account", tx.toAccount);
        // BigDecimal ghi thẳng: ở JSON Lines không có lý do gì phải hạ xuống
        // double như khi ghi Parquet.
        node.put("amount_received", tx.amountReceived);
        node.put("receiving_currency", tx.receivingCurrency);
        node.put("amount_paid", tx.amountPaid);
        node.put("payment_currency", tx.paymentCurrency);
        node.put("payment_format", tx.paymentFormat);
        if (tx.isLaundering == null) {
            node.putNull("is_laundering");
        } else {
            node.put("is_laundering", tx.isLaundering);
        }
        node.put("source_dataset", tx.sourceDataset);
        node.put("source_file", tx.sourceFile);
        node.put("source_line_number", tx.sourceLineNumber);
        node.put("ingested_at", tx.ingestedAt);
        node.put("schema_version", tx.schemaVersion);
        node.put("flink_processed_at", tx.flinkProcessedAt);
        node.put("event_date", tx.eventDate);
        node.put("event_hour", tx.eventHour);
        node.put("kafka_partition", tx.kafkaPartition);
        node.put("kafka_offset", tx.kafkaOffset);
        return write(node);
    }

    public String rejectedToJson(RejectedRecord record) {
        ObjectNode node = mapper().createObjectNode();
        node.put("error_type", record.errorType);
        node.put("error_message", record.errorMessage);
        node.put("stage", record.stage);
        node.put("kafka_topic", record.kafkaTopic);
        node.put("kafka_partition", record.kafkaPartition);
        node.put("kafka_offset", record.kafkaOffset);
        node.put("kafka_timestamp", record.kafkaTimestamp);
        node.put("transaction_id", record.transactionId);
        node.put("source_file", record.sourceFile);
        node.put("source_line_number", record.sourceLineNumber);
        node.put("event_date", record.eventDate);
        node.put("rejected_at", record.rejectedAt);
        node.put("raw_payload", record.rawPayload);
        return write(node);
    }

    private String write(ObjectNode node) {
        try {
            return mapper().writeValueAsString(node);
        } catch (JsonProcessingException ex) {
            // Node được dựng từ các kiểu cơ bản nên nhánh này không xảy ra
            // trong thực tế; ném lên chứ không nuốt, để nếu nó xảy ra thì
            // job dừng chứ không ghi ra file rỗng.
            throw new IllegalStateException("Không tuần tự hoá được bản ghi sang JSON", ex);
        }
    }
}
