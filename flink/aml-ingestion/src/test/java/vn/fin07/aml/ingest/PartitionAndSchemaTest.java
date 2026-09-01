package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import org.apache.avro.generic.GenericDatumWriter;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.EncoderFactory;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.sink.AvroSchemas;
import vn.fin07.aml.ingest.sink.PartitionPaths;

/** Trường thời gian phái sinh, đường dẫn phân vùng, và bản ghi Avro ghi xuống HDFS. */
class PartitionAndSchemaTest {

    @Test
    void eventDateAndHourComeFromEventTimeInUtc() {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.eventTimeEpochMs = 1661990580000L; // 2022-09-01T00:03:00Z
        tx.deriveTimeFields();
        assertEquals("2022-09-01", tx.eventDate);
        assertEquals("00", tx.eventHour);
        assertNotNull(tx.flinkProcessedAt);
    }

    @Test
    void hourBoundaryLandsInTheRightPartition() {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.eventTimeEpochMs = 1662076799000L; // 2022-09-01T23:59:59Z
        tx.deriveTimeFields();
        assertEquals("2022-09-01", tx.eventDate);
        assertEquals("23", tx.eventHour);

        tx.eventTimeEpochMs = 1662076800000L; // 2022-09-02T00:00:00Z
        tx.deriveTimeFields();
        assertEquals("2022-09-02", tx.eventDate);
        assertEquals("00", tx.eventHour);
    }

    @Test
    void kafkaMetadataIsCarriedThrough() {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.assignKafkaMetadata(3, 987654L);
        assertEquals(3, tx.kafkaPartition);
        assertEquals(987654L, tx.kafkaOffset);
    }

    @Test
    void bucketPathHasThreePartitionKeys() {
        assertEquals(
                "source_dataset=HI-Small/event_date=2022-09-01/event_hour=00",
                PartitionPaths.transactionBucket("HI-Small", "2022-09-01", "00"));
    }

    @Test
    void rejectedBucketIsByDateAndErrorType() {
        assertEquals(
                "event_date=2026-07-31/error_type=json_unparsable",
                PartitionPaths.rejectedBucket("2026-07-31", "json_unparsable"));
    }

    @Test
    void partitionValuesCannotEscapeTheDirectory() {
        String bucket = PartitionPaths.transactionBucket("../../etc", "2022-09-01", "00");
        assertFalse(bucket.contains(".."));
        assertFalse(bucket.contains("/etc"));
    }

    @Test
    void emptyPartitionValueBecomesUnknown() {
        assertTrue(PartitionPaths.transactionBucket("", "2022-09-01", "00").contains("source_dataset=unknown"));
    }

    @Test
    void avroRecordCarriesEveryColumn() {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.assignKafkaMetadata(1, 42L);
        tx.deriveTimeFields();

        GenericRecord record = AvroSchemas.toRecord(tx);
        assertEquals("015768", record.get("from_bank").toString());
        assertEquals("8149656B0", record.get("from_account").toString());
        assertEquals(10.91d, (double) record.get("amount_received"), 1e-9);
        assertEquals(0, record.get("is_laundering"));
        assertEquals("HI-Small", record.get("source_dataset").toString());
        assertEquals(2L, record.get("source_line_number"));
        assertEquals(1, record.get("kafka_partition"));
        assertEquals(42L, record.get("kafka_offset"));
        assertEquals(23, AvroSchemas.transactionSchema().getFields().size());
    }

    @Test
    void avroRecordSerialises() throws Exception {
        // Bản ghi phải tuần tự hoá được thì FileSink mới ghi xuống HDFS được;
        // một trường thiếu hoặc sai kiểu chỉ lộ ra ở đúng bước này.
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.deriveTimeFields();
        GenericRecord record = AvroSchemas.toRecord(tx);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        BinaryEncoder encoder = EncoderFactory.get().binaryEncoder(out, null);
        new GenericDatumWriter<GenericRecord>(AvroSchemas.transactionSchema()).write(record, encoder);
        encoder.flush();
        assertTrue(out.size() > 0);
    }

    @Test
    void canonicalRecordSerialisesWithoutLaunderingLabel() throws Exception {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.transactionId = "TXN-S000-0000000001";
        tx.isLaundering = null;
        tx.deriveTimeFields();
        GenericRecord record = AvroSchemas.toRecord(tx);
        assertEquals(null, record.get("is_laundering"));

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        BinaryEncoder encoder = EncoderFactory.get().binaryEncoder(out, null);
        new GenericDatumWriter<GenericRecord>(AvroSchemas.transactionSchema()).write(record, encoder);
        encoder.flush();
        assertTrue(out.size() > 0);
    }

    @Test
    void amountKeepsItsValueThroughTheDoubleColumn() {
        AmlTransaction tx = TransactionValidatorTest.valid();
        tx.amountPaid = new BigDecimal("0.00000340");
        tx.amountReceived = new BigDecimal("89999999.99");
        tx.deriveTimeFields();

        GenericRecord record = AvroSchemas.toRecord(tx);
        // So sánh bằng compareTo chứ không bằng equals: cột Parquet là kiểu
        // double nên số chữ số thập phân không còn được giữ, nhưng *giá trị*
        // thì phải nguyên vẹn — đó mới là điều cần chứng minh ở đây.
        assertEquals(
                0,
                new BigDecimal("0.00000340").compareTo(new BigDecimal(String.valueOf(record.get("amount_paid")))));
        assertEquals(
                0,
                new BigDecimal("89999999.99")
                        .compareTo(new BigDecimal(String.valueOf(record.get("amount_received")))));
    }
}
