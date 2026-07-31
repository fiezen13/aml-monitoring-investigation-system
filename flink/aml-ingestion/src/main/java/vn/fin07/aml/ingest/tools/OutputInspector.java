package vn.fin07.aml.ingest.tools;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;
import java.util.TreeSet;
import org.apache.avro.generic.GenericRecord;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileStatus;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.LocatedFileStatus;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RemoteIterator;
import org.apache.parquet.avro.AvroParquetReader;
import org.apache.parquet.hadoop.ParquetReader;
import org.apache.parquet.hadoop.util.HadoopInputFile;

/**
 * Đọc lại dữ liệu đã ghi xuống HDFS và in ra số liệu đối chiếu.
 *
 * <pre>
 * java -cp "/opt/flink/usrlib/aml-ingestion.jar:$HADOOP_CLASSPATH" \
 *      vn.fin07.aml.ingest.tools.OutputInspector hdfs://namenode:8020/data/aml/bronze/transactions
 * </pre>
 *
 * <p>Công cụ này tồn tại vì một lý do: "job chạy không lỗi" và "dữ liệu ghi
 * ra đọc lại được, đúng số lượng, đúng giá trị" là hai chuyện khác nhau, và
 * chỉ chuyện thứ hai mới đáng gọi là xong. Kiểm tra khói dùng chính nó để
 * đối chiếu số bản ghi vào với số bản ghi ra.
 *
 * <p>Đọc được cả Parquet lẫn JSON Lines, tuỳ theo {@code AML_HDFS_FORMAT}
 * mà job đã ghi. Đầu ra dạng {@code khoá=giá trị}, mỗi dòng một khoá, để
 * script shell lấy bằng {@code grep} mà không phải phân tích gì.
 */
public final class OutputInspector {

    private OutputInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Cách dùng: OutputInspector <đường-dẫn-hdfs> [số-bản-ghi-mẫu]");
            System.exit(2);
        }
        String target = args[0];
        int sampleSize = args.length > 1 ? Integer.parseInt(args[1]) : 1;

        Configuration conf = new Configuration();
        Path root = new Path(target);
        FileSystem fs = root.getFileSystem(conf);

        if (!fs.exists(root)) {
            System.out.println("path_exists=false");
            System.out.println("records=0");
            System.out.println("files=0");
            return;
        }
        System.out.println("path_exists=true");

        List<Path> parquet = new ArrayList<>();
        List<Path> jsonl = new ArrayList<>();
        int inProgress = 0;

        RemoteIterator<LocatedFileStatus> files = fs.listFiles(root, true);
        while (files.hasNext()) {
            FileStatus status = files.next();
            String name = status.getPath().getName();
            if (name.contains("inprogress") || name.startsWith(".") || name.startsWith("_")) {
                inProgress++;
                continue;
            }
            if (name.endsWith(".parquet")) {
                parquet.add(status.getPath());
            } else if (name.endsWith(".jsonl")) {
                jsonl.add(status.getPath());
            }
        }

        System.out.println("files=" + (parquet.size() + jsonl.size()));
        System.out.println("files_parquet=" + parquet.size());
        System.out.println("files_jsonl=" + jsonl.size());
        System.out.println("files_in_progress=" + inProgress);

        Stats stats = new Stats();
        for (Path path : parquet) {
            readParquet(path, conf, stats, sampleSize);
        }
        for (Path path : jsonl) {
            readJsonLines(fs, path, stats, sampleSize);
        }

        stats.print();
    }

    private static void readParquet(Path path, Configuration conf, Stats stats, int sampleSize) throws IOException {
        try (ParquetReader<GenericRecord> reader =
                AvroParquetReader.<GenericRecord>builder(HadoopInputFile.fromPath(path, conf))
                        .withConf(conf)
                        .build()) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                stats.observe(
                        str(record, "transaction_id"),
                        str(record, "from_bank"),
                        str(record, "from_account"),
                        str(record, "event_time"),
                        str(record, "source_dataset"),
                        str(record, "event_date"),
                        str(record, "event_hour"),
                        Integer.parseInt(str(record, "is_laundering")),
                        new BigDecimal(str(record, "amount_paid")));
                if (stats.samples.size() < sampleSize) {
                    stats.samples.add(record.toString());
                }
            }
        }
    }

    private static void readJsonLines(FileSystem fs, Path path, Stats stats, int sampleSize) throws IOException {
        try (BufferedReader reader =
                new BufferedReader(new InputStreamReader(fs.open(path), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                stats.observe(
                        jsonString(line, "transaction_id"),
                        jsonString(line, "from_bank"),
                        jsonString(line, "from_account"),
                        jsonString(line, "event_time"),
                        jsonString(line, "source_dataset"),
                        jsonString(line, "event_date"),
                        jsonString(line, "event_hour"),
                        Integer.parseInt(jsonNumber(line, "is_laundering")),
                        new BigDecimal(jsonNumber(line, "amount_paid")));
                if (stats.samples.size() < sampleSize) {
                    stats.samples.add(line);
                }
            }
        }
    }

    private static String str(GenericRecord record, String field) {
        Object value = record.get(field);
        return value == null ? "" : value.toString();
    }

    /** Bóc một giá trị chuỗi khỏi dòng JSON mà không kéo thêm thư viện nào. */
    private static String jsonString(String line, String field) {
        String key = "\"" + field + "\":\"";
        int start = line.indexOf(key);
        if (start < 0) {
            return "";
        }
        start += key.length();
        int end = line.indexOf('"', start);
        return end < 0 ? "" : line.substring(start, end);
    }

    private static String jsonNumber(String line, String field) {
        String key = "\"" + field + "\":";
        int start = line.indexOf(key);
        if (start < 0) {
            return "0";
        }
        start += key.length();
        int end = start;
        while (end < line.length() && "-+.0123456789eE".indexOf(line.charAt(end)) >= 0) {
            end++;
        }
        return start == end ? "0" : line.substring(start, end);
    }

    /** Số liệu tổng hợp, đủ để đối chiếu với phía producer. */
    private static final class Stats {
        long records;
        long laundering;
        final TreeSet<String> transactionIds = new TreeSet<>();
        final TreeSet<String> datasets = new TreeSet<>();
        final TreeMap<String, Long> byPartition = new TreeMap<>();
        final TreeSet<String> banksWithLeadingZero = new TreeSet<>();
        final List<String> samples = new ArrayList<>();
        String minEventTime = null;
        String maxEventTime = null;
        BigDecimal amountTotal = BigDecimal.ZERO;

        void observe(
                String transactionId,
                String fromBank,
                String fromAccount,
                String eventTime,
                String dataset,
                String eventDate,
                String eventHour,
                int isLaundering,
                BigDecimal amountPaid) {
            records++;
            if (isLaundering == 1) {
                laundering++;
            }
            transactionIds.add(transactionId);
            datasets.add(dataset);
            byPartition.merge(dataset + "/" + eventDate + "/" + eventHour, 1L, Long::sum);
            if (fromBank.length() > 1 && fromBank.startsWith("0")) {
                banksWithLeadingZero.add(fromBank);
            }
            if (minEventTime == null || eventTime.compareTo(minEventTime) < 0) {
                minEventTime = eventTime;
            }
            if (maxEventTime == null || eventTime.compareTo(maxEventTime) > 0) {
                maxEventTime = eventTime;
            }
            amountTotal = amountTotal.add(amountPaid);
        }

        void print() {
            System.out.println("records=" + records);
            System.out.println("distinct_transaction_ids=" + transactionIds.size());
            System.out.println("laundering_label_1=" + laundering);
            System.out.println("laundering_label_0=" + (records - laundering));
            System.out.println("datasets=" + String.join(",", datasets));
            System.out.println("partitions=" + byPartition.size());
            System.out.println("banks_with_leading_zero=" + banksWithLeadingZero.size());
            System.out.println("min_event_time=" + (minEventTime == null ? "-" : minEventTime));
            System.out.println("max_event_time=" + (maxEventTime == null ? "-" : maxEventTime));
            System.out.println(String.format(Locale.ROOT, "amount_paid_total=%s", amountTotal.toPlainString()));
            for (String sample : samples) {
                System.out.println("sample=" + sample);
            }
        }
    }
}
