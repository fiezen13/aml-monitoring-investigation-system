package vn.fin07.aml.ingest.config;

import java.io.Serializable;
import java.util.Map;
import org.apache.flink.api.java.utils.ParameterTool;

/**
 * Cấu hình của job, gộp từ ba nguồn theo thứ tự ưu tiên tăng dần:
 * giá trị mặc định → biến môi trường → tham số dòng lệnh.
 *
 * <p>Không có giá trị nào bị ghi cứng trong logic xử lý. Lý do rất thực tế:
 * cùng một jar này chạy ở máy cá nhân, ở CI và ở cụm thật, và ba nơi đó khác
 * nhau ở địa chỉ broker, đường dẫn HDFS và mức song song — chứ không khác
 * nhau ở mã nguồn.
 */
public final class JobConfig implements Serializable {

    private static final long serialVersionUID = 1L;

    /** Kafka. */
    public final String bootstrapServers;
    public final String rawTopic;
    public final String consumerGroupId;
    public final String offsetReset;

    /** Thời gian và checkpoint. */
    public final long checkpointIntervalMs;
    public final long watermarkOutOfOrderSeconds;
    public final long idlenessSeconds;
    public final int restartAttempts;
    public final long restartDelaySeconds;

    /** HDFS. */
    public final String hdfsBasePath;
    public final String outputFormat;
    public final long rolloverIntervalMs;
    public final long rolloverInactivityMs;
    public final long rolloverMaxBytes;

    /** Khác. */
    public final String expectedSchemaVersion;
    public final int parallelism;

    private JobConfig(Resolver resolver) {
        this.bootstrapServers = resolver.get("kafka.bootstrap.servers", "KAFKA_BOOTSTRAP_SERVERS", "kafka:9092");
        this.rawTopic = resolver.get("aml.raw.topic", "AML_RAW_TOPIC", "aml.transactions.raw.v1");
        this.consumerGroupId = resolver.get("aml.group.id", "AML_FLINK_GROUP_ID", "aml-hdfs-ingestion-v1");
        this.offsetReset = resolver.get("aml.offset.reset", "AML_KAFKA_OFFSET_RESET", "earliest");

        this.checkpointIntervalMs = resolver.getLong("aml.checkpoint.interval.ms", "AML_CHECKPOINT_INTERVAL_MS", 30_000L);
        this.watermarkOutOfOrderSeconds =
                resolver.getLong("aml.watermark.out.of.order.seconds", "AML_WATERMARK_OUT_OF_ORDER_SECONDS", 120L);
        this.idlenessSeconds = resolver.getLong("aml.watermark.idle.seconds", "AML_WATERMARK_IDLE_SECONDS", 60L);
        this.restartAttempts = (int) resolver.getLong("aml.restart.attempts", "AML_RESTART_ATTEMPTS", 10L);
        this.restartDelaySeconds = resolver.getLong("aml.restart.delay.seconds", "AML_RESTART_DELAY_SECONDS", 10L);

        this.hdfsBasePath = resolver.get("aml.hdfs.base.path", "AML_HDFS_BASE_PATH", "hdfs://namenode:8020/data/aml");
        this.outputFormat = resolver.get("aml.hdfs.format", "AML_HDFS_FORMAT", "parquet").toLowerCase();
        this.rolloverIntervalMs = resolver.getLong("aml.rollover.interval.ms", "AML_ROLLOVER_INTERVAL_MS", 300_000L);
        this.rolloverInactivityMs = resolver.getLong("aml.rollover.inactivity.ms", "AML_ROLLOVER_INACTIVITY_MS", 120_000L);
        this.rolloverMaxBytes = resolver.getLong("aml.rollover.max.mb", "AML_ROLLOVER_MAX_MB", 128L) * 1024L * 1024L;

        this.expectedSchemaVersion = resolver.get("aml.schema.version", "AML_SCHEMA_VERSION", "1.0");
        this.parallelism = (int) resolver.getLong("aml.parallelism", "AML_FLINK_PARALLELISM", 2L);

        if (!"parquet".equals(outputFormat) && !"json".equals(outputFormat)) {
            throw new IllegalArgumentException(
                    "AML_HDFS_FORMAT phải là 'parquet' hoặc 'json', nhận được: " + outputFormat);
        }
    }

    public static JobConfig fromArgs(String[] args) {
        return new JobConfig(new Resolver(ParameterTool.fromArgs(args), System.getenv()));
    }

    public static JobConfig fromMaps(Map<String, String> params, Map<String, String> env) {
        return new JobConfig(new Resolver(ParameterTool.fromMap(params), env));
    }

    /** Đường dẫn dữ liệu hợp lệ, tầng bronze. */
    public String transactionsPath() {
        return trimTrailingSlash(hdfsBasePath) + "/bronze/transactions";
    }

    /** Đường dẫn bản ghi bị từ chối. */
    public String rejectedPath() {
        return trimTrailingSlash(hdfsBasePath) + "/rejected/transactions";
    }

    private static String trimTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    @Override
    public String toString() {
        return "JobConfig{"
                + "bootstrapServers=" + bootstrapServers
                + ", rawTopic=" + rawTopic
                + ", consumerGroupId=" + consumerGroupId
                + ", offsetReset=" + offsetReset
                + ", checkpointIntervalMs=" + checkpointIntervalMs
                + ", watermarkOutOfOrderSeconds=" + watermarkOutOfOrderSeconds
                + ", hdfsBasePath=" + hdfsBasePath
                + ", outputFormat=" + outputFormat
                + ", parallelism=" + parallelism
                + ", expectedSchemaVersion=" + expectedSchemaVersion
                + '}';
    }

    /** Tra cứu theo thứ tự: tham số dòng lệnh → biến môi trường → mặc định. */
    private static final class Resolver {
        private final ParameterTool params;
        private final Map<String, String> env;

        Resolver(ParameterTool params, Map<String, String> env) {
            this.params = params;
            this.env = env;
        }

        String get(String paramName, String envName, String fallback) {
            if (params.has(paramName)) {
                return params.get(paramName);
            }
            String fromEnv = env.get(envName);
            return fromEnv != null && !fromEnv.isEmpty() ? fromEnv : fallback;
        }

        long getLong(String paramName, String envName, long fallback) {
            String raw = get(paramName, envName, String.valueOf(fallback));
            try {
                return Long.parseLong(raw.trim());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(envName + " phải là số nguyên, nhận được: " + raw, ex);
            }
        }
    }
}
