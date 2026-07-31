package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collectors;
import org.apache.flink.streaming.runtime.streamrecord.StreamRecord;
import org.apache.flink.streaming.util.OneInputStreamOperatorTestHarness;
import org.apache.flink.streaming.util.ProcessFunctionTestHarnesses;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.config.JobConfig;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.model.IngestedRecord;
import vn.fin07.aml.ingest.model.RejectedRecord;
import vn.fin07.aml.ingest.serde.TransactionJsonParser;

/**
 * Bước kiểm tra và tách nhánh, chạy trên test harness của Flink.
 *
 * <p>Điều cần chứng minh: mỗi bản ghi vào đều đi ra đúng một nhánh. Không có
 * bản ghi nào bốc hơi, kể cả bản ghi hỏng.
 */
class ValidateAndSplitTest {

    private static JobConfig config() {
        Map<String, String> env = new HashMap<>();
        env.put("AML_RAW_TOPIC", "aml.transactions.raw.v1");
        return JobConfig.fromMaps(Collections.emptyMap(), env);
    }

    private static OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness() throws Exception {
        return ProcessFunctionTestHarnesses.forProcessFunction(new AmlIngestionJob.ValidateAndSplit(config()));
    }

    private static IngestedRecord parsed(String json) throws Exception {
        AmlTransaction tx = new TransactionJsonParser().parse(json);
        tx.assignKafkaMetadata(0, 17L);
        return IngestedRecord.valid(tx);
    }

    @Test
    void validRecordGoesToTheMainOutputWithPartitionFields() throws Exception {
        try (OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness = harness()) {
            harness.processElement(new StreamRecord<>(parsed(TransactionJsonParserTest.validJson())));

            List<AmlTransaction> out = harness.extractOutputValues();
            assertEquals(1, out.size());
            assertEquals("2022-09-01", out.get(0).eventDate);
            assertEquals("00", out.get(0).eventHour);
            assertNotNull(out.get(0).flinkProcessedAt);
            assertEquals(0, sideOutput(harness).size());
        }
    }

    @Test
    void deserialisationFailureGoesToTheSideOutput() throws Exception {
        try (OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness = harness()) {
            RejectedRecord failure = RejectedRecord.of(
                    "json_unparsable", "hỏng", "{không phải json", "aml.transactions.raw.v1", 0, 5L, 123L);
            harness.processElement(new StreamRecord<>(IngestedRecord.invalid(failure)));

            assertEquals(0, harness.extractOutputValues().size());
            List<RejectedRecord> rejected = sideOutput(harness);
            assertEquals(1, rejected.size());
            assertEquals("json_unparsable", rejected.get(0).errorType);
            assertEquals(5L, rejected.get(0).kafkaOffset);
        }
    }

    @Test
    void validationFailureGoesToTheSideOutputWithTraceability() throws Exception {
        try (OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness = harness()) {
            String json = TransactionJsonParserTest.validJson().replace("\"schema_version\":\"1.0\"", "\"schema_version\":\"9.9\"");
            harness.processElement(new StreamRecord<>(parsed(json)));

            assertEquals(0, harness.extractOutputValues().size());
            RejectedRecord rejected = sideOutput(harness).get(0);
            assertEquals("schema_version_mismatch", rejected.errorType);
            assertEquals("HI-Small_Trans.csv", rejected.sourceFile);
            assertEquals(2L, rejected.sourceLineNumber);
            assertEquals("9d3f1c0a8b6e4f27a51d0c93e7b4a812", rejected.transactionId);
            assertTrue(rejected.rawPayload.contains("\"from_bank\":\"015768\""));
        }
    }

    @Test
    void everyRecordLeavesOnExactlyOneBranch() throws Exception {
        try (OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness = harness()) {
            harness.processElement(new StreamRecord<>(parsed(TransactionJsonParserTest.validJson())));
            harness.processElement(new StreamRecord<>(
                    parsed(TransactionJsonParserTest.validJson().replace("\"is_laundering\":0", "\"is_laundering\":7"))));
            harness.processElement(new StreamRecord<>(IngestedRecord.invalid(
                    RejectedRecord.of("empty_payload", "trống", "", "t", 0, 1L, 1L))));

            int valid = harness.extractOutputValues().size();
            int invalid = sideOutput(harness).size();
            assertEquals(3, valid + invalid);
            assertEquals(1, valid);
            assertEquals(2, invalid);
        }
    }

    @Test
    void launderingLabelDoesNotChangeRouting() throws Exception {
        try (OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness = harness()) {
            harness.processElement(new StreamRecord<>(
                    parsed(TransactionJsonParserTest.validJson().replace("\"is_laundering\":0", "\"is_laundering\":1"))));

            List<AmlTransaction> out = harness.extractOutputValues();
            assertEquals(1, out.size());
            assertEquals(1, out.get(0).isLaundering);
            assertEquals(0, sideOutput(harness).size());
        }
    }

    /** Nhánh phụ, đã bóc khỏi lớp bọc StreamRecord. Rỗng khi chưa có gì đi ra. */
    private static List<RejectedRecord> sideOutput(
            OneInputStreamOperatorTestHarness<IngestedRecord, AmlTransaction> harness) {
        ConcurrentLinkedQueue<StreamRecord<RejectedRecord>> queue =
                harness.getSideOutput(AmlIngestionJob.REJECTED);
        if (queue == null) {
            return Collections.emptyList();
        }
        return queue.stream().map(StreamRecord::getValue).collect(Collectors.toList());
    }
}
