package vn.fin07.aml.ingest.sink;

import java.io.Serializable;

/**
 * Một dòng JSON kèm thư mục phân vùng mà nó thuộc về.
 *
 * <p>FileSink ở chế độ row-format nhận vào một phần tử và hỏi
 * {@code BucketAssigner} xem phần tử đó nằm ở thư mục nào. Nếu phần tử chỉ
 * là một {@code String} JSON thì bộ gán thư mục sẽ phải phân tích lại JSON
 * cho từng bản ghi — đúng công việc vừa làm xong, làm lại lần nữa. Ghép sẵn
 * khoá phân vùng vào cạnh nội dung sẽ tránh được điều đó.
 */
public class JsonLine implements Serializable {

    private static final long serialVersionUID = 1L;

    public String bucket;
    public String json;

    public JsonLine() {
        // Flink cần constructor rỗng.
    }

    public JsonLine(String bucket, String json) {
        this.bucket = bucket;
        this.json = json;
    }
}
