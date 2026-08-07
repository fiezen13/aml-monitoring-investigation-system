package vn.fin07.aml.ingest;

import java.time.Duration;
import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.MapFunction;
import org.apache.flink.api.common.functions.OpenContext;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.configuration.RestartStrategyOptions;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.formats.avro.typeutils.GenericRecordAvroTypeInfo;
import org.apache.flink.metrics.Counter;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import vn.fin07.aml.ingest.config.JobConfig;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.model.IngestedRecord;
import vn.fin07.aml.ingest.model.RejectedRecord;
import vn.fin07.aml.ingest.serde.IngestedRecordDeserializer;
import vn.fin07.aml.ingest.sink.AvroSchemas;
import vn.fin07.aml.ingest.sink.JsonEncoders;
import vn.fin07.aml.ingest.sink.JsonLine;
import vn.fin07.aml.ingest.sink.PartitionPaths;
import vn.fin07.aml.ingest.sink.SinkFactory;
import vn.fin07.aml.ingest.validation.TransactionValidator;

/**
 * Job nạp dữ liệu: {@code aml.transactions.raw.v1} → HDFS.
 *
 * <pre>
 *   Kafka ──▶ giải mã ──▶ kiểm tra ──┬──▶ event time + watermark ──▶ HDFS bronze
 *                                    └──▶ side output ────────────▶ HDFS rejected
 * </pre>
 *
 * <p><b>Job này chỉ nạp dữ liệu.</b> Không có ngưỡng số tiền, không gộp theo
 * tài khoản, không cửa sổ trượt, không dò chu trình, không fan-in/fan-out,
 * không chấm điểm rủi ro, không suy luận mô hình, không dựng đồ thị, không
 * sinh cảnh báo. Nhãn {@code is_laundering} của hợp đồng legacy đi qua như
 * một cột dữ liệu; sự kiện ABM Bank View không mang nhãn và được ghi là null.
 *
 * <p>Event time và watermark được khai báo dù giai đoạn này chưa có cửa sổ
 * nào: chúng thuộc về *hợp đồng của luồng dữ liệu*, và gắn sẵn từ bây giờ
 * thì các phép tính theo thời gian sau này không phải nạp lại toàn bộ dữ liệu
 * để có được một trục thời gian đúng.
 */
public final class AmlIngestionJob {

    private static final Logger LOG = LoggerFactory.getLogger(AmlIngestionJob.class);

    /** Nhánh phụ cho bản ghi không dùng được. */
    public static final OutputTag<RejectedRecord> REJECTED = new OutputTag<RejectedRecord>("rejected") {};

    private AmlIngestionJob() {}

    public static void main(String[] args) throws Exception {
        JobConfig config = JobConfig.fromArgs(args);
        LOG.info("Khởi động job nạp AML với cấu hình {}", config);

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment(restartConfig(config));
        env.setParallelism(config.parallelism);

        // Checkpoint là thứ khiến FileSink chuyển file từ `in-progress` sang
        // hoàn tất. Tắt checkpoint thì dữ liệu sẽ nằm mãi ở trạng thái dở
        // dang và không job nào đọc được — nên nó không phải tuỳ chọn.
        env.enableCheckpointing(config.checkpointIntervalMs);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(config.checkpointIntervalMs / 2);
        env.getCheckpointConfig().setCheckpointTimeout(Math.max(config.checkpointIntervalMs * 4, 60_000L));
        env.getCheckpointConfig().setTolerableCheckpointFailureNumber(3);

        KafkaSource<IngestedRecord> source = KafkaSource.<IngestedRecord>builder()
                .setBootstrapServers(config.bootstrapServers)
                .setTopics(config.rawTopic)
                .setGroupId(config.consumerGroupId)
                .setStartingOffsets(startingOffsets(config.offsetReset))
                .setDeserializer(new IngestedRecordDeserializer())
                // Thêm partition cho topic khi đang chạy thì job tự nhận ra,
                // không phải khởi động lại.
                .setProperty("partition.discovery.interval.ms", "60000")
                .build();

        SingleOutputStreamOperator<AmlTransaction> validated = env.fromSource(
                        source, WatermarkStrategy.noWatermarks(), "kafka:" + config.rawTopic)
                .process(new ValidateAndSplit(config))
                .name("kiểm tra và tách nhánh")
                .uid("validate-and-split");

        DataStream<RejectedRecord> rejected = validated.getSideOutput(REJECTED);

        // Watermark gắn *sau* bước kiểm tra: một bản ghi có event time vô
        // nghĩa mà lọt vào đây sẽ kéo watermark đi hàng chục năm và làm mọi
        // cửa sổ về sau vô dụng.
        DataStream<AmlTransaction> timed = validated
                .assignTimestampsAndWatermarks(
                        WatermarkStrategy.<AmlTransaction>forBoundedOutOfOrderness(
                                        Duration.ofSeconds(config.watermarkOutOfOrderSeconds))
                                .withTimestampAssigner((event, timestamp) -> event.eventTimeEpochMs)
                                .withIdleness(Duration.ofSeconds(config.idlenessSeconds)))
                .name("event time và watermark")
                .uid("assign-watermarks");

        if ("parquet".equals(config.outputFormat)) {
            timed.map(AvroSchemas::toRecord)
                    .returns(new GenericRecordAvroTypeInfo(AvroSchemas.transactionSchema()))
                    .name("sang bản ghi Avro")
                    .uid("to-avro")
                    .sinkTo(SinkFactory.parquetTransactions(config))
                    .name("HDFS bronze (parquet)")
                    .uid("sink-bronze-parquet");
        } else {
            timed.map(new TransactionToJsonLine())
                    .name("sang JSON Lines")
                    .uid("to-jsonl")
                    .sinkTo(SinkFactory.jsonTransactions(config))
                    .name("HDFS bronze (jsonl)")
                    .uid("sink-bronze-json");
        }

        rejected.map(new RejectedToJsonLine())
                .name("bản ghi bị từ chối sang JSON")
                .uid("rejected-to-jsonl")
                .sinkTo(SinkFactory.rejected(config))
                .name("HDFS rejected")
                .uid("sink-rejected");

        env.execute("FIN-07 AML ingestion (kafka → hdfs)");
    }

    private static Configuration restartConfig(JobConfig config) {
        Configuration conf = new Configuration();
        conf.set(RestartStrategyOptions.RESTART_STRATEGY, "fixed-delay");
        conf.set(RestartStrategyOptions.RESTART_STRATEGY_FIXED_DELAY_ATTEMPTS, config.restartAttempts);
        conf.set(
                RestartStrategyOptions.RESTART_STRATEGY_FIXED_DELAY_DELAY,
                Duration.ofSeconds(config.restartDelaySeconds));
        return conf;
    }

    static OffsetsInitializer startingOffsets(String offsetReset) {
        // `committedOffsets` là hành vi đúng cho một job chạy dài: lần đầu
        // thì lấy theo chiến lược đặt ở đây, những lần sau thì tiếp tục từ
        // chỗ consumer group đã đi tới.
        switch (offsetReset.trim().toLowerCase()) {
            case "latest":
                return OffsetsInitializer.committedOffsets(OffsetResetStrategy.LATEST);
            case "none":
                return OffsetsInitializer.committedOffsets(OffsetResetStrategy.NONE);
            case "earliest":
            default:
                return OffsetsInitializer.committedOffsets(OffsetResetStrategy.EARLIEST);
        }
    }

    /**
     * Kiểm tra từng bản ghi và tách thành hai nhánh.
     *
     * <p>Không bản ghi nào biến mất ở đây: mỗi bản ghi vào hoặc ra nhánh
     * chính, hoặc ra nhánh phụ, và cả hai nhánh đều có bộ đếm.
     */
    public static final class ValidateAndSplit extends ProcessFunction<IngestedRecord, AmlTransaction> {
        private static final long serialVersionUID = 1L;

        private final JobConfig config;
        private final TransactionValidator validator;
        private final JsonEncoders encoders = new JsonEncoders();

        private transient Counter consumed;
        private transient Counter valid;
        private transient Counter invalid;
        private transient Counter deserializationFailures;

        public ValidateAndSplit(JobConfig config) {
            this.config = config;
            this.validator = new TransactionValidator(config.expectedSchemaVersion);
        }

        @Override
        public void open(OpenContext openContext) {
            var group = getRuntimeContext().getMetricGroup().addGroup("aml");
            consumed = group.counter("recordsConsumed");
            valid = group.counter("recordsValid");
            invalid = group.counter("recordsInvalid");
            deserializationFailures = group.counter("deserializationFailures");
        }

        @Override
        public void processElement(IngestedRecord record, Context ctx, Collector<AmlTransaction> out) {
            consumed.inc();

            if (!record.isValid()) {
                deserializationFailures.inc();
                invalid.inc();
                ctx.output(REJECTED, record.rejected);
                return;
            }

            AmlTransaction tx = record.transaction;
            TransactionValidator.Violation violation = validator.validate(tx);
            if (violation != null) {
                invalid.inc();
                ctx.output(
                        REJECTED,
                        RejectedRecord.of(
                                        violation.errorType,
                                        violation.message,
                                        encoders.transactionToJson(tx),
                                        config.rawTopic,
                                        tx.kafkaPartition,
                                        tx.kafkaOffset,
                                        -1L)
                                .withSource(tx.transactionId, tx.sourceFile, tx.sourceLineNumber));
                return;
            }

            tx.deriveTimeFields();
            valid.inc();
            out.collect(tx);
        }
    }

    /** Giao dịch hợp lệ → dòng JSON kèm thư mục phân vùng. */
    public static final class TransactionToJsonLine implements MapFunction<AmlTransaction, JsonLine> {
        private static final long serialVersionUID = 1L;
        private final JsonEncoders encoders = new JsonEncoders();

        @Override
        public JsonLine map(AmlTransaction tx) {
            return new JsonLine(
                    PartitionPaths.transactionBucket(tx.sourceDataset, tx.eventDate, tx.eventHour),
                    encoders.transactionToJson(tx));
        }
    }

    /** Bản ghi bị từ chối → dòng JSON kèm thư mục phân vùng. */
    public static final class RejectedToJsonLine implements MapFunction<RejectedRecord, JsonLine> {
        private static final long serialVersionUID = 1L;
        private final JsonEncoders encoders = new JsonEncoders();

        @Override
        public JsonLine map(RejectedRecord record) {
            return new JsonLine(
                    PartitionPaths.rejectedBucket(record.eventDate, record.errorType),
                    encoders.rejectedToJson(record));
        }
    }
}
