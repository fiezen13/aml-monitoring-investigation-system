package vn.fin07.aml.ingest.sink;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.serialization.Encoder;
import org.apache.flink.configuration.MemorySize;
import org.apache.flink.connector.file.sink.FileSink;
import org.apache.flink.core.fs.Path;
import org.apache.flink.formats.parquet.avro.AvroParquetWriters;
import org.apache.flink.streaming.api.functions.sink.filesystem.BucketAssigner;
import org.apache.flink.streaming.api.functions.sink.filesystem.OutputFileConfig;
import org.apache.flink.streaming.api.functions.sink.filesystem.bucketassigners.SimpleVersionedStringSerializer;
import org.apache.flink.streaming.api.functions.sink.filesystem.rollingpolicies.DefaultRollingPolicy;
import org.apache.flink.streaming.api.functions.sink.filesystem.rollingpolicies.OnCheckpointRollingPolicy;
import vn.fin07.aml.ingest.config.JobConfig;

/**
 * Dựng các {@link FileSink} ghi xuống HDFS.
 *
 * <p><b>Chính sách cắt file.</b> Hai định dạng có hai cơ chế khác nhau, và
 * đây là ràng buộc của Flink chứ không phải lựa chọn:
 *
 * <ul>
 *   <li><i>Parquet</i> là định dạng khối (bulk). Flink chỉ cho phép cắt file
 *       tại checkpoint, vì một file Parquet dở dang không đọc được. Vậy nên
 *       {@code AML_CHECKPOINT_INTERVAL_MS} chính là thứ quyết định kích
 *       thước file: khoảng 30 giây cho file vừa phải, vài phút nếu muốn ít
 *       file to.
 *   <li><i>JSON Lines</i> là định dạng dòng, cắt được theo thời gian, theo
 *       khoảng lặng và theo kích thước — ba biến {@code AML_ROLLOVER_*}.
 * </ul>
 *
 * <p>Trong cả hai trường hợp, file chỉ được đổi từ trạng thái {@code
 * in-progress} sang {@code finished} sau khi checkpoint thành công. Đó là
 * điều khiến job đọc phía sau không bao giờ thấy một file viết dở.
 */
public final class SinkFactory {

    private SinkFactory() {}

    public static FileSink<GenericRecord> parquetTransactions(JobConfig config) {
        return FileSink.forBulkFormat(
                        new Path(config.transactionsPath()),
                        AvroParquetWriters.forGenericRecord(AvroSchemas.transactionSchema()))
                .withBucketAssigner(new TransactionBucketAssigner())
                .withRollingPolicy(OnCheckpointRollingPolicy.build())
                .withOutputFileConfig(
                        OutputFileConfig.builder().withPartPrefix("transactions").withPartSuffix(".parquet").build())
                .build();
    }

    public static FileSink<JsonLine> jsonTransactions(JobConfig config) {
        return jsonLines(config.transactionsPath(), config, "transactions");
    }

    public static FileSink<JsonLine> rejected(JobConfig config) {
        return jsonLines(config.rejectedPath(), config, "rejected");
    }

    private static FileSink<JsonLine> jsonLines(String path, JobConfig config, String prefix) {
        return FileSink.forRowFormat(new Path(path), new JsonLineEncoder())
                .withBucketAssigner(new JsonLineBucketAssigner())
                .withRollingPolicy(DefaultRollingPolicy.builder()
                        .withRolloverInterval(Duration.ofMillis(config.rolloverIntervalMs))
                        .withInactivityInterval(Duration.ofMillis(config.rolloverInactivityMs))
                        .withMaxPartSize(new MemorySize(config.rolloverMaxBytes))
                        .build())
                // Điều kiện cắt file theo thời gian chỉ được *kiểm tra* mỗi
                // khoảng này (mặc định của Flink là 60 giây). Để nguyên thì
                // đặt `AML_ROLLOVER_INACTIVITY_MS=10000` cũng không có tác
                // dụng gì — file vẫn nằm dở tới tận phút sau. Suy ra từ chính
                // hai ngưỡng kia để chúng nói đúng điều chúng hứa.
                .withBucketCheckInterval(bucketCheckInterval(config))
                .withOutputFileConfig(
                        OutputFileConfig.builder().withPartPrefix(prefix).withPartSuffix(".jsonl").build())
                .build();
    }

    /**
     * Nhịp kiểm tra điều kiện cắt file, bằng nửa ngưỡng thời gian nhỏ nhất.
     *
     * <p>Chặn dưới ở 1 giây: kiểm tra dày hơn thế chỉ tốn thêm timer chứ
     * không giúp gì, vì file vẫn phải chờ checkpoint mới được chốt.
     */
    public static long bucketCheckInterval(JobConfig config) {
        return Math.max(1_000L, Math.min(config.rolloverIntervalMs, config.rolloverInactivityMs) / 2);
    }

    /** Ghi mỗi bản ghi thành một dòng JSON. */
    public static final class JsonLineEncoder implements Encoder<JsonLine> {
        private static final long serialVersionUID = 1L;

        @Override
        public void encode(JsonLine element, OutputStream stream) throws IOException {
            stream.write(element.json.getBytes(StandardCharsets.UTF_8));
            stream.write('\n');
        }
    }

    /** Thư mục của bản ghi Parquet, lấy từ chính ba cột phân vùng. */
    public static final class TransactionBucketAssigner implements BucketAssigner<GenericRecord, String> {
        private static final long serialVersionUID = 1L;

        @Override
        public String getBucketId(GenericRecord element, Context context) {
            return PartitionPaths.transactionBucket(
                    String.valueOf(element.get("source_dataset")),
                    String.valueOf(element.get("event_date")),
                    String.valueOf(element.get("event_hour")));
        }

        @Override
        public SimpleVersionedStringSerializer getSerializer() {
            return SimpleVersionedStringSerializer.INSTANCE;
        }
    }

    /** Thư mục đã được tính sẵn ở bước chuyển sang JSON. */
    public static final class JsonLineBucketAssigner implements BucketAssigner<JsonLine, String> {
        private static final long serialVersionUID = 1L;

        @Override
        public String getBucketId(JsonLine element, Context context) {
            return element.bucket;
        }

        @Override
        public SimpleVersionedStringSerializer getSerializer() {
            return SimpleVersionedStringSerializer.INSTANCE;
        }
    }
}
