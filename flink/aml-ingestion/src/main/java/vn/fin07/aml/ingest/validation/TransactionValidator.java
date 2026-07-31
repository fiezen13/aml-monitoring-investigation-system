package vn.fin07.aml.ingest.validation;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.regex.Pattern;
import vn.fin07.aml.ingest.model.AmlTransaction;

/**
 * Kiểm tra lại sự kiện ở phía Flink, sau khi producer đã kiểm tra một lần.
 *
 * <p>Kiểm tra hai lần không thừa: producer và Flink là hai tiến trình được
 * triển khai độc lập, và topic có thể nhận dữ liệu từ một producer khác,
 * một phiên bản cũ, hoặc một lần chạy thử tay. Tầng lưu trữ phải tự bảo vệ
 * được lược đồ của chính nó.
 *
 * <p><b>Không có luật AML nào ở đây.</b> Không ngưỡng số tiền, không gộp
 * theo tài khoản, không chấm điểm. Nhãn {@code is_laundering} chỉ được kiểm
 * tra là 0 hoặc 1 — đúng như kiểm tra kiểu dữ liệu của bất kỳ cột nào khác —
 * và không hề tham gia vào việc quyết định bản ghi đi đâu.
 */
public final class TransactionValidator implements Serializable {

    private static final long serialVersionUID = 1L;

    private static final Pattern TRANSACTION_ID = Pattern.compile("^[0-9a-f]{32}$");

    /** 2000-01-01 và 2100-01-01 tính bằng mili giây. */
    private static final long MIN_EVENT_TIME_MS = 946_684_800_000L;
    private static final long MAX_EVENT_TIME_MS = 4_102_444_800_000L;

    private final String expectedSchemaVersion;

    public TransactionValidator(String expectedSchemaVersion) {
        this.expectedSchemaVersion = expectedSchemaVersion;
    }

    /** Kết quả kiểm tra: {@code null} nghĩa là hợp lệ. */
    public static final class Violation implements Serializable {
        private static final long serialVersionUID = 1L;
        public final String errorType;
        public final String message;

        Violation(String errorType, String message) {
            this.errorType = errorType;
            this.message = message;
        }
    }

    public Violation validate(AmlTransaction tx) {
        if (!expectedSchemaVersion.equals(tx.schemaVersion)) {
            return new Violation(
                    "schema_version_mismatch",
                    "Cần lược đồ " + expectedSchemaVersion + ", nhận được " + tx.schemaVersion);
        }
        if (tx.transactionId == null || !TRANSACTION_ID.matcher(tx.transactionId).matches()) {
            return new Violation("transaction_id_invalid", "transaction_id không đúng dạng: " + tx.transactionId);
        }
        if (tx.eventTimeEpochMs < MIN_EVENT_TIME_MS || tx.eventTimeEpochMs > MAX_EVENT_TIME_MS) {
            return new Violation(
                    "event_time_out_of_range",
                    "event_time_epoch_ms ngoài khoảng hợp lý: " + tx.eventTimeEpochMs);
        }
        Violation identifier = checkIdentifiers(tx);
        if (identifier != null) {
            return identifier;
        }
        Violation amount = checkAmount(tx.amountReceived, "amount_received");
        if (amount != null) {
            return amount;
        }
        amount = checkAmount(tx.amountPaid, "amount_paid");
        if (amount != null) {
            return amount;
        }
        if (isBlank(tx.receivingCurrency) || isBlank(tx.paymentCurrency)) {
            return new Violation("currency_missing", "Thiếu đơn vị tiền tệ");
        }
        if (isBlank(tx.paymentFormat)) {
            return new Violation("payment_format_missing", "Thiếu payment_format");
        }
        if (tx.isLaundering != 0 && tx.isLaundering != 1) {
            return new Violation("label_invalid", "is_laundering phải là 0 hoặc 1, nhận được " + tx.isLaundering);
        }
        if (isBlank(tx.sourceFile) || tx.sourceLineNumber < 2) {
            return new Violation(
                    "source_reference_invalid",
                    "Thiếu tham chiếu nguồn (source_file / source_line_number)");
        }
        if (isBlank(tx.sourceDataset)) {
            return new Violation("source_dataset_missing", "Thiếu source_dataset — không phân vùng được");
        }
        return null;
    }

    private static Violation checkIdentifiers(AmlTransaction tx) {
        if (isBlank(tx.fromBank) || isBlank(tx.fromAccount) || isBlank(tx.toBank) || isBlank(tx.toAccount)) {
            return new Violation("identifier_missing", "Thiếu định danh ngân hàng hoặc tài khoản");
        }
        return null;
    }

    private static Violation checkAmount(BigDecimal amount, String field) {
        if (amount == null) {
            return new Violation("amount_missing", "Thiếu " + field);
        }
        if (amount.signum() < 0) {
            return new Violation("amount_negative", field + " âm: " + amount.toPlainString());
        }
        return null;
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
