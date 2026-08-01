package vn.fin07.aml.ingest.sink;

/**
 * Đường dẫn phân vùng trên HDFS.
 *
 * <p>Dữ liệu hợp lệ:
 *
 * <pre>
 * /data/aml/bronze/transactions/source_dataset=HI-Small/event_date=2022-09-01/event_hour=00/
 * </pre>
 *
 * <p>Dữ liệu bị từ chối:
 *
 * <pre>
 * /data/aml/rejected/transactions/event_date=2026-07-31/error_type=json_unparsable/
 * </pre>
 *
 * <p>Ba khoá phân vùng — bộ dữ liệu, ngày, giờ — là mức chi tiết vừa đủ:
 * truy vấn theo khoảng thời gian chỉ phải đọc đúng phần cần đọc, mà số thư
 * mục vẫn ở mức hàng nghìn. <b>Không</b> phân vùng theo tài khoản: bộ dữ
 * liệu có hàng trăm nghìn tài khoản, và mỗi tài khoản một thư mục sẽ tạo ra
 * hàng trăm nghìn file rất nhỏ — thứ mà NameNode phải giữ toàn bộ trong bộ
 * nhớ, và thứ làm mọi job đọc sau này chậm đi hàng chục lần.
 */
public final class PartitionPaths {

    private PartitionPaths() {}

    public static String transactionBucket(String sourceDataset, String eventDate, String eventHour) {
        return "source_dataset=" + sanitize(sourceDataset)
                + "/event_date=" + sanitize(eventDate)
                + "/event_hour=" + sanitize(eventHour);
    }

    public static String rejectedBucket(String eventDate, String errorType) {
        return "event_date=" + sanitize(eventDate) + "/error_type=" + sanitize(errorType);
    }

    /**
     * Làm sạch một giá trị trước khi đưa vào đường dẫn.
     *
     * <p>Giá trị phân vùng đến từ dữ liệu, và dữ liệu thì có thể chứa bất cứ
     * thứ gì. Một {@code source_dataset} chứa dấu {@code /} sẽ đẻ thêm một
     * tầng thư mục ngoài ý muốn; chứa {@code ..} thì trỏ ra ngoài thư mục
     * gốc. Chỉ giữ chữ, số, gạch ngang và gạch dưới — dấu chấm cũng bị loại,
     * vì không tên bộ dữ liệu hay mốc thời gian nào cần tới nó, còn
     * {@code ..} thì chỉ cần dấu chấm là dựng lại được.
     */
    static String sanitize(String value) {
        if (value == null || value.trim().isEmpty()) {
            return "unknown";
        }
        String cleaned = value.trim().replaceAll("[^A-Za-z0-9_-]", "_");
        return cleaned.isEmpty() ? "unknown" : cleaned;
    }
}
