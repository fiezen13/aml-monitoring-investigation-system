package vn.fin07.aml.ingest.sink;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import vn.fin07.aml.ingest.model.AmlTransaction;

/**
 * Lược đồ Avro của tầng bronze trên HDFS, và cách đổi một
 * {@link AmlTransaction} sang bản ghi Avro để ghi Parquet.
 *
 * <p>Tên cột giữ nguyên dạng snake_case của hợp đồng dữ liệu JSON, không đổi
 * sang camelCase của Java: file Parquet sẽ được Spark, Hive và pandas đọc,
 * và tên cột ở đó phải khớp tài liệu lược đồ chứ không khớp quy ước đặt tên
 * của một ngôn ngữ.
 *
 * <p><b>Về số tiền.</b> Hai cột số tiền được ghi kiểu {@code double}. Parquet
 * có kiểu DECIMAL, nhưng đường ghi Avro → Parquet của Flink dùng
 * {@code GenericData.get()} vốn không đăng ký sẵn bộ chuyển đổi decimal, nên
 * dùng DECIMAL ở đây sẽ hỏng lúc chạy chứ không phải lúc biên dịch. Đổi lại,
 * producer chỉ ghi ra số JSON khi giá trị quay ngược lại đúng bằng chính nó
 * (dưới 15 chữ số có nghĩa — đúng với toàn bộ bộ dữ liệu IBM), nên vòng
 * decimal → JSON → double không làm sai con số. Xem mục giới hạn trong
 * contracts/ingestion/README.md.
 */
public final class AvroSchemas {

    private AvroSchemas() {}

    public static final String TRANSACTION_SCHEMA_JSON = "{"
            + "\"type\":\"record\","
            + "\"name\":\"AmlTransactionBronze\","
            + "\"namespace\":\"vn.fin07.aml\","
            + "\"doc\":\"Giao dịch AML tầng bronze, một bản ghi cho một dòng CSV nguồn\","
            + "\"fields\":["
            + "{\"name\":\"transaction_id\",\"type\":\"string\"},"
            + "{\"name\":\"event_time\",\"type\":\"string\"},"
            + "{\"name\":\"event_time_epoch_ms\",\"type\":\"long\"},"
            + "{\"name\":\"from_bank\",\"type\":\"string\"},"
            + "{\"name\":\"from_account\",\"type\":\"string\"},"
            + "{\"name\":\"to_bank\",\"type\":\"string\"},"
            + "{\"name\":\"to_account\",\"type\":\"string\"},"
            + "{\"name\":\"amount_received\",\"type\":\"double\"},"
            + "{\"name\":\"receiving_currency\",\"type\":\"string\"},"
            + "{\"name\":\"amount_paid\",\"type\":\"double\"},"
            + "{\"name\":\"payment_currency\",\"type\":\"string\"},"
            + "{\"name\":\"payment_format\",\"type\":\"string\"},"
            + "{\"name\":\"is_laundering\",\"type\":\"int\"},"
            + "{\"name\":\"source_dataset\",\"type\":\"string\"},"
            + "{\"name\":\"source_file\",\"type\":\"string\"},"
            + "{\"name\":\"source_line_number\",\"type\":\"long\"},"
            + "{\"name\":\"ingested_at\",\"type\":\"string\"},"
            + "{\"name\":\"schema_version\",\"type\":\"string\"},"
            + "{\"name\":\"flink_processed_at\",\"type\":\"string\"},"
            + "{\"name\":\"event_date\",\"type\":\"string\"},"
            + "{\"name\":\"event_hour\",\"type\":\"string\"},"
            + "{\"name\":\"kafka_partition\",\"type\":\"int\"},"
            + "{\"name\":\"kafka_offset\",\"type\":\"long\"}"
            + "]}";

    private static final Schema SCHEMA = new Schema.Parser().parse(TRANSACTION_SCHEMA_JSON);

    public static Schema transactionSchema() {
        return SCHEMA;
    }

    public static GenericRecord toRecord(AmlTransaction tx) {
        GenericRecord record = new GenericData.Record(SCHEMA);
        record.put("transaction_id", tx.transactionId);
        record.put("event_time", tx.eventTime);
        record.put("event_time_epoch_ms", tx.eventTimeEpochMs);
        record.put("from_bank", tx.fromBank);
        record.put("from_account", tx.fromAccount);
        record.put("to_bank", tx.toBank);
        record.put("to_account", tx.toAccount);
        record.put("amount_received", tx.amountReceived.doubleValue());
        record.put("receiving_currency", tx.receivingCurrency);
        record.put("amount_paid", tx.amountPaid.doubleValue());
        record.put("payment_currency", tx.paymentCurrency);
        record.put("payment_format", tx.paymentFormat);
        record.put("is_laundering", tx.isLaundering);
        record.put("source_dataset", tx.sourceDataset);
        record.put("source_file", tx.sourceFile);
        record.put("source_line_number", tx.sourceLineNumber);
        record.put("ingested_at", tx.ingestedAt);
        record.put("schema_version", tx.schemaVersion);
        record.put("flink_processed_at", tx.flinkProcessedAt);
        record.put("event_date", tx.eventDate);
        record.put("event_hour", tx.eventHour);
        record.put("kafka_partition", tx.kafkaPartition);
        record.put("kafka_offset", tx.kafkaOffset);
        return record;
    }
}
