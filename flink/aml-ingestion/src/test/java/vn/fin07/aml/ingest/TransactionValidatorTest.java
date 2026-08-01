package vn.fin07.aml.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import vn.fin07.aml.ingest.model.AmlTransaction;
import vn.fin07.aml.ingest.validation.TransactionValidator;

/**
 * Kiểm tra lại ở phía Flink.
 *
 * <p>Nửa sau của file này quan trọng ngang nửa đầu: nó khẳng định những gì
 * validator **không** làm. Một bộ kiểm tra âm thầm loại giao dịch đáng ngờ
 * sẽ làm hỏng bộ dữ liệu theo cách không ai phát hiện ra, vì phần bị mất
 * đúng là phần người ta quan tâm nhất.
 */
class TransactionValidatorTest {

    private final TransactionValidator validator = new TransactionValidator("1.0");

    static AmlTransaction valid() {
        AmlTransaction tx = new AmlTransaction();
        tx.transactionId = "9d3f1c0a8b6e4f27a51d0c93e7b4a812";
        tx.eventTime = "2022-09-01T00:03:00";
        tx.eventTimeEpochMs = 1661990580000L;
        tx.fromBank = "015768";
        tx.fromAccount = "8149656B0";
        tx.toBank = "070";
        tx.toAccount = "80A1B2C30";
        tx.amountReceived = new BigDecimal("10.91");
        tx.receivingCurrency = "US Dollar";
        tx.amountPaid = new BigDecimal("10.91");
        tx.paymentCurrency = "US Dollar";
        tx.paymentFormat = "Reinvestment";
        tx.isLaundering = 0;
        tx.sourceDataset = "HI-Small";
        tx.sourceFile = "HI-Small_Trans.csv";
        tx.sourceLineNumber = 2;
        tx.ingestedAt = "2026-07-31T08:12:44.512Z";
        tx.schemaVersion = "1.0";
        return tx;
    }

    @Test
    void acceptsAWellFormedTransaction() {
        assertNull(validator.validate(valid()));
    }

    @Test
    void rejectsWrongSchemaVersion() {
        AmlTransaction tx = valid();
        tx.schemaVersion = "2.0";
        assertEquals("schema_version_mismatch", validator.validate(tx).errorType);
    }

    @Test
    void rejectsMalformedTransactionId() {
        AmlTransaction tx = valid();
        tx.transactionId = "KHÔNG-PHẢI-HEX";
        assertEquals("transaction_id_invalid", validator.validate(tx).errorType);
    }

    @Test
    void rejectsEventTimeOutOfRange() {
        AmlTransaction tx = valid();
        tx.eventTimeEpochMs = 0L;
        assertEquals("event_time_out_of_range", validator.validate(tx).errorType);
    }

    @Test
    void rejectsMissingIdentifier() {
        AmlTransaction tx = valid();
        tx.toAccount = "  ";
        assertEquals("identifier_missing", validator.validate(tx).errorType);
    }

    @Test
    void rejectsNegativeAmount() {
        AmlTransaction tx = valid();
        tx.amountPaid = new BigDecimal("-0.01");
        assertEquals("amount_negative", validator.validate(tx).errorType);
    }

    @Test
    void rejectsMissingCurrency() {
        AmlTransaction tx = valid();
        tx.receivingCurrency = "";
        assertEquals("currency_missing", validator.validate(tx).errorType);
    }

    @Test
    void rejectsLabelOutsideZeroAndOne() {
        AmlTransaction tx = valid();
        tx.isLaundering = 2;
        assertEquals("label_invalid", validator.validate(tx).errorType);
    }

    @Test
    void rejectsMissingSourceReference() {
        AmlTransaction tx = valid();
        tx.sourceLineNumber = 0;
        assertEquals("source_reference_invalid", validator.validate(tx).errorType);
    }

    // ---- Những gì validator KHÔNG được làm ----

    @Test
    void keepsTransactionsLabelledAsLaundering() {
        AmlTransaction tx = valid();
        tx.isLaundering = 1;
        assertNull(validator.validate(tx));
    }

    @Test
    void keepsSelfTransfers() {
        AmlTransaction tx = valid();
        tx.toBank = tx.fromBank;
        tx.toAccount = tx.fromAccount;
        assertNull(validator.validate(tx));
    }

    @Test
    void keepsVerySmallAndVeryLargeAmounts() {
        AmlTransaction tiny = valid();
        tiny.amountPaid = new BigDecimal("0.00000001");
        tiny.amountReceived = new BigDecimal("0.00000001");
        assertNull(validator.validate(tiny));

        AmlTransaction huge = valid();
        huge.amountPaid = new BigDecimal("987654321987.65");
        huge.amountReceived = new BigDecimal("987654321987.65");
        assertNull(validator.validate(huge));
    }

    @Test
    void keepsZeroAmounts() {
        AmlTransaction tx = valid();
        tx.amountPaid = BigDecimal.ZERO;
        tx.amountReceived = BigDecimal.ZERO;
        assertNull(validator.validate(tx));
    }

    @Test
    void keepsCrossCurrencyTransactions() {
        AmlTransaction tx = valid();
        tx.paymentCurrency = "Bitcoin";
        tx.amountPaid = new BigDecimal("0.00000340");
        assertNull(validator.validate(tx));
    }

    @Test
    void violationCarriesAMessage() {
        AmlTransaction tx = valid();
        tx.schemaVersion = "0.9";
        assertNotNull(validator.validate(tx).message);
    }
}
