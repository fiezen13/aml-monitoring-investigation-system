package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.serde.TransactionJsonParser;

/** Giải mã JSON của lược đồ v1.0. */
class TransactionJsonParserTest {

    private final TransactionJsonParser parser = new TransactionJsonParser();

    static String validJson() {
        return "{"
                + "\"transaction_id\":\"9d3f1c0a8b6e4f27a51d0c93e7b4a812\","
                + "\"event_time\":\"2022-09-01T00:03:00\","
                + "\"event_time_epoch_ms\":1661990580000,"
                + "\"from_bank\":\"015768\","
                + "\"from_account\":\"8149656B0\","
                + "\"to_bank\":\"015768\","
                + "\"to_account\":\"8149656B0\","
                + "\"amount_received\":10.91,"
                + "\"receiving_currency\":\"US Dollar\","
                + "\"amount_paid\":10.91,"
                + "\"payment_currency\":\"US Dollar\","
                + "\"payment_format\":\"Reinvestment\","
                + "\"is_laundering\":0,"
                + "\"source_dataset\":\"HI-Small\","
                + "\"source_file\":\"HI-Small_Trans.csv\","
                + "\"source_line_number\":2,"
                + "\"ingested_at\":\"2026-07-31T08:12:44.512Z\","
                + "\"schema_version\":\"1.0\"}";
    }

    @Test
    void readsEveryFieldOfTheContract() throws Exception {
        AmlTransaction tx = parser.parse(validJson());
        assertEquals("9d3f1c0a8b6e4f27a51d0c93e7b4a812", tx.transactionId);
        assertEquals(1661990580000L, tx.eventTimeEpochMs);
        assertEquals("015768", tx.fromBank);
        assertEquals("8149656B0", tx.toAccount);
        assertEquals("US Dollar", tx.paymentCurrency);
        assertEquals(0, tx.isLaundering);
        assertEquals(2L, tx.sourceLineNumber);
        assertEquals("1.0", tx.schemaVersion);
    }

    @Test
    void leadingZeroOfBankIdSurvives() throws Exception {
        assertEquals("015768", parser.parse(validJson()).fromBank);
    }

    @Test
    void amountsAreReadAsBigDecimalNotDouble() throws Exception {
        String json = validJson().replace("\"amount_paid\":10.91", "\"amount_paid\":0.00000340");
        AmlTransaction tx = parser.parse(json);
        assertEquals(new BigDecimal("0.00000340"), tx.amountPaid);
        assertEquals(new BigDecimal("10.91"), tx.amountReceived);
    }

    @Test
    void bankIdWrittenAsANumberIsRejected() {
        // Đây chính là cái bẫy mà lược đồ tồn tại để chặn: một producer khác
        // ghi mã ngân hàng thành số thì số 0 ở đầu đã mất trước khi tới đây.
        String json = validJson().replace("\"from_bank\":\"015768\"", "\"from_bank\":15768");
        TransactionJsonParser.ParseException ex =
                assertThrows(TransactionJsonParser.ParseException.class, () -> parser.parse(json));
        assertEquals("type_mismatch", ex.errorType());
    }

    @Test
    void missingFieldIsReported() {
        String json = validJson().replace("\"payment_format\":\"Reinvestment\",", "");
        TransactionJsonParser.ParseException ex =
                assertThrows(TransactionJsonParser.ParseException.class, () -> parser.parse(json));
        assertEquals("missing_field", ex.errorType());
    }

    @Test
    void unknownFieldIsNotSilentlyDropped() {
        String json = validJson().replace("{", "{\"risk_score\":0.93,");
        TransactionJsonParser.ParseException ex =
                assertThrows(TransactionJsonParser.ParseException.class, () -> parser.parse(json));
        assertEquals("unexpected_field", ex.errorType());
    }

    @Test
    void malformedJsonIsReported() {
        TransactionJsonParser.ParseException ex =
                assertThrows(TransactionJsonParser.ParseException.class, () -> parser.parse("{đây không phải json"));
        assertEquals("json_unparsable", ex.errorType());
    }

    @Test
    void nonObjectPayloadIsReported() {
        TransactionJsonParser.ParseException ex =
                assertThrows(TransactionJsonParser.ParseException.class, () -> parser.parse("[1,2,3]"));
        assertEquals("json_not_an_object", ex.errorType());
    }
}
