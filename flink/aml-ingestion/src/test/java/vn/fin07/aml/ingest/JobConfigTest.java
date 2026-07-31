package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.config.JobConfig;

/** Cấu hình: mặc định, biến môi trường, tham số dòng lệnh. */
class JobConfigTest {

    @Test
    void defaultsAreUsableWithoutAnyConfiguration() {
        JobConfig config = JobConfig.fromMaps(Collections.emptyMap(), Collections.emptyMap());
        assertEquals("kafka:9092", config.bootstrapServers);
        assertEquals("aml.transactions.raw.v1", config.rawTopic);
        assertEquals("aml-hdfs-ingestion-v1", config.consumerGroupId);
        assertEquals("parquet", config.outputFormat);
        assertEquals(120L, config.watermarkOutOfOrderSeconds);
        assertEquals("1.0", config.expectedSchemaVersion);
    }

    @Test
    void environmentOverridesDefaults() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_HDFS_BASE_PATH", "hdfs://other:8020/lake/aml");
        env.put("AML_HDFS_FORMAT", "json");
        env.put("AML_CHECKPOINT_INTERVAL_MS", "5000");

        JobConfig config = JobConfig.fromMaps(Collections.emptyMap(), env);
        assertEquals("json", config.outputFormat);
        assertEquals(5000L, config.checkpointIntervalMs);
        assertEquals("hdfs://other:8020/lake/aml/bronze/transactions", config.transactionsPath());
        assertEquals("hdfs://other:8020/lake/aml/rejected/transactions", config.rejectedPath());
    }

    @Test
    void commandLineOverridesEnvironment() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_RAW_TOPIC", "từ-môi-trường");
        Map<String, String> params = new HashMap<>();
        params.put("aml.raw.topic", "từ-dòng-lệnh");

        assertEquals("từ-dòng-lệnh", JobConfig.fromMaps(params, env).rawTopic);
    }

    @Test
    void trailingSlashInBasePathDoesNotDoubleUp() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_HDFS_BASE_PATH", "hdfs://namenode:8020/data/aml/");
        assertEquals(
                "hdfs://namenode:8020/data/aml/bronze/transactions",
                JobConfig.fromMaps(Collections.emptyMap(), env).transactionsPath());
    }

    @Test
    void unknownOutputFormatFailsFast() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_HDFS_FORMAT", "orc");
        assertThrows(
                IllegalArgumentException.class, () -> JobConfig.fromMaps(Collections.emptyMap(), env));
    }

    @Test
    void nonNumericIntervalFailsFast() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_CHECKPOINT_INTERVAL_MS", "ba mươi giây");
        assertThrows(
                IllegalArgumentException.class, () -> JobConfig.fromMaps(Collections.emptyMap(), env));
    }
}
