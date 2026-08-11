package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.config.JobConfig;
import vn.fin07.aml.ingest.sink.SinkFactory;

/** Dựng sink, và nhịp kiểm tra điều kiện cắt file. */
class SinkFactoryTest {

    private static JobConfig config(Map<String, String> env) {
        return JobConfig.fromMaps(Collections.emptyMap(), env);
    }

    @Test
    void bucketCheckIntervalNeverExceedsTheShortestThreshold() {
        // Đây là bài kiểm thử của một lỗi có thật: mặc định của Flink là kiểm
        // tra 60 giây một lần, nên đặt khoảng lặng 10 giây mà không chỉnh
        // nhịp kiểm tra thì file vẫn nằm dở tới tận phút sau.
        Map<String, String> env = new HashMap<>();
        env.put("AML_ROLLOVER_INTERVAL_MS", "15000");
        env.put("AML_ROLLOVER_INACTIVITY_MS", "10000");

        long interval = SinkFactory.bucketCheckInterval(config(env));
        assertEquals(5_000L, interval);
        assertTrue(interval <= 10_000L);
    }

    @Test
    void bucketCheckIntervalHasAFloor() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_ROLLOVER_INTERVAL_MS", "100");
        env.put("AML_ROLLOVER_INACTIVITY_MS", "100");
        assertEquals(1_000L, SinkFactory.bucketCheckInterval(config(env)));
    }

    @Test
    void parquetSinkBuilds() {
        // Sink dùng đường dẫn file:// để dựng được mà không cần cụm HDFS;
        // điều cần kiểm là lược đồ Avro và bộ gán thư mục ghép được với nhau.
        Map<String, String> env = new HashMap<>();
        env.put("AML_HDFS_BASE_PATH", "file:///tmp/aml-test");
        assertNotNull(SinkFactory.parquetTransactions(config(env)));
    }

    @Test
    void jsonSinksBuild() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_HDFS_BASE_PATH", "file:///tmp/aml-test");
        env.put("AML_HDFS_FORMAT", "json");
        JobConfig config = config(env);
        assertNotNull(SinkFactory.jsonTransactions(config));
        assertNotNull(SinkFactory.rejected(config));
    }
}
