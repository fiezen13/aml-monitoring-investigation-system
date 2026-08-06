package vn.fin07.aml.ingest.serde;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import java.util.TreeSet;
import vn.fin07.aml.ingest.model.AmlTransaction;

/**
 * Đọc JSON của lược đồ chuẩn hoá v1.0 thành {@link AmlTransaction}.
 *
 * <p>Hai lựa chọn đáng nói ở đây:
 *
 * <ol>
 *   <li><b>Số tiền đọc bằng {@link BigDecimal}.</b> Jackson mặc định đọc số
 *       thập phân thành {@code double}; với dữ liệu tài chính thì đó là chỗ
 *       sai số bắt đầu. {@code USE_BIG_DECIMAL_FOR_FLOATS} giữ đúng con số
 *       như nó xuất hiện trong JSON.
 *   <li><b>Trường lạ là lỗi, không phải chuyện bỏ qua được.</b> Lược đồ có
 *       phiên bản; thêm trường mà không tăng phiên bản là một thay đổi
 *       không khai báo, và bỏ qua nó trong im lặng sẽ khiến dữ liệu mới bị
 *       cắt xén mà phía dưới không hay biết.
 * </ol>
 */
public final class TransactionJsonParser implements Serializable {

    private static final long serialVersionUID = 1L;

    /** Tên trường bắt buộc, đúng theo contracts/ingestion/aml-transaction-v1.schema.json. */
    private static final Set<String> KNOWN_FIELDS = new HashSet<>(Arrays.asList(
            "transaction_id",
            "event_time",
            "event_time_epoch_ms",
            "from_bank",
            "from_account",
            "to_bank",
            "to_account",
            "amount_received",
            "receiving_currency",
            "amount_paid",
            "payment_currency",
            "payment_format",
            "is_laundering",
            "source_dataset",
            "source_file",
            "source_line_number",
            "ingested_at",
            "schema_version"));

    private transient ObjectMapper mapper;

    /** Lỗi đọc JSON, mang theo loại lỗi để phân vùng vùng dữ liệu bị từ chối. */
    public static final class ParseException extends Exception {
        private static final long serialVersionUID = 1L;
        private final String errorType;

        public ParseException(String errorType, String message) {
            super(message);
            this.errorType = errorType;
        }

        public String errorType() {
            return errorType;
        }
    }

    private ObjectMapper mapper() {
        if (mapper == null) {
            mapper = new ObjectMapper()
                    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
                    // Mặc định Jackson cắt số 0 ở đuôi phần thập phân, biến
                    // `0.00000340` thành `0.0000034`. Giá trị vẫn bằng nhau
                    // về mặt số học, nhưng số chữ số thập phân là thông tin
                    // của chính bản ghi — nó nói lên đơn vị tiền được ghi ở
                    // mức chính xác nào — nên giữ nguyên.
                    .setNodeFactory(JsonNodeFactory.withExactBigDecimals(true));
        }
        return mapper;
    }

    public AmlTransaction parse(String payload) throws ParseException {
        JsonNode root;
        try {
            root = mapper().readTree(payload);
        } catch (Exception ex) {
            throw new ParseException("json_unparsable", "Không đọc được JSON: " + ex.getMessage());
        }
        if (root == null || !root.isObject()) {
            throw new ParseException("json_not_an_object", "Payload không phải một đối tượng JSON");
        }

        Set<String> unexpected = new TreeSet<>();
        for (Iterator<String> names = root.fieldNames(); names.hasNext(); ) {
            String name = names.next();
            if (!KNOWN_FIELDS.contains(name)) {
                unexpected.add(name);
            }
        }
        if (!unexpected.isEmpty()) {
            throw new ParseException(
                    "unexpected_field",
                    "Trường không thuộc lược đồ v1.0: " + String.join(", ", unexpected));
        }

        AmlTransaction transaction = new AmlTransaction();
        transaction.transactionId = text(root, "transaction_id");
        transaction.eventTime = text(root, "event_time");
        transaction.eventTimeEpochMs = longValue(root, "event_time_epoch_ms");
        transaction.fromBank = text(root, "from_bank");
        transaction.fromAccount = text(root, "from_account");
        transaction.toBank = text(root, "to_bank");
        transaction.toAccount = text(root, "to_account");
        transaction.amountReceived = decimal(root, "amount_received");
        transaction.receivingCurrency = text(root, "receiving_currency");
        transaction.amountPaid = decimal(root, "amount_paid");
        transaction.paymentCurrency = text(root, "payment_currency");
        transaction.paymentFormat = text(root, "payment_format");
        transaction.isLaundering = (int) longValue(root, "is_laundering");
        transaction.sourceDataset = text(root, "source_dataset");
        transaction.sourceFile = text(root, "source_file");
        transaction.sourceLineNumber = longValue(root, "source_line_number");
        transaction.ingestedAt = text(root, "ingested_at");
        transaction.schemaVersion = text(root, "schema_version");
        return transaction;
    }

    private static JsonNode require(JsonNode root, String field) throws ParseException {
        JsonNode node = root.get(field);
        if (node == null || node.isNull()) {
            throw new ParseException("missing_field", "Thiếu trường bắt buộc: " + field);
        }
        return node;
    }

    private static String text(JsonNode root, String field) throws ParseException {
        JsonNode node = require(root, field);
        if (!node.isTextual()) {
            // Bắt đúng cái bẫy của bộ dữ liệu này: mã ngân hàng bị ghi thành
            // số thì `015768` đã mất số 0 ở đầu từ trước khi tới đây.
            throw new ParseException("type_mismatch", "Trường " + field + " phải là chuỗi, nhận được " + node.getNodeType());
        }
        return node.asText();
    }

    private static long longValue(JsonNode root, String field) throws ParseException {
        JsonNode node = require(root, field);
        if (!node.isIntegralNumber()) {
            throw new ParseException(
                    "type_mismatch", "Trường " + field + " phải là số nguyên, nhận được " + node.getNodeType());
        }
        return node.asLong();
    }

    private static BigDecimal decimal(JsonNode root, String field) throws ParseException {
        JsonNode node = require(root, field);
        if (!node.isNumber()) {
            throw new ParseException(
                    "type_mismatch", "Trường " + field + " phải là số, nhận được " + node.getNodeType());
        }
        return node.decimalValue();
    }
}
