#!/usr/bin/env bash
# Kiểm tra khói luồng nạp AML: CSV → Kafka → Flink → HDFS.
#
#   ./scripts/aml/smoke_test.sh
#
# Không phải kiểm tra "container còn sống". Từng bước dưới đây đi qua một
# mắt xích thật, và bước cuối cùng đọc lại dữ liệu từ HDFS rồi đối chiếu số
# lượng với đầu vào. Mã thoát khác 0 nghĩa là có mắt xích đứt.
#
# Dữ liệu dùng cho phép thử là file mẫu 204 dòng trong tests/fixtures/aml/,
# không phải bộ dữ liệu thật — nên chạy được trên máy chưa tải gì từ Kaggle.
# Trong đó cố ý có: giao dịch hợp lệ, nhãn 0 và 1, giao dịch tự chuyển cho
# chính mình, giao dịch khác đơn vị tiền, và bốn dòng hỏng.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=ci/lib.sh
source "${REPO_ROOT}/ci/lib.sh"

cd "$REPO_ROOT"

COMPOSE="${COMPOSE:-docker compose}"
AML="$COMPOSE --profile aml"

FIXTURE_DIR="${REPO_ROOT}/tests/fixtures/aml"
FIXTURE_FILE="HI-Sample_Trans.csv"
EXPECTED_VALID=200
EXPECTED_INVALID=4

# Topic và thư mục riêng cho mỗi lượt chạy, dọn sạch khi xong.
#
# Không dùng topic thật: một lượt kiểm tra khói phải cho ra cùng con số dù
# chạy lần thứ nhất hay lần thứ mười, mà topic thật thì giữ lại dữ liệu của
# những lượt trước — job đọc từ `earliest` sẽ đếm cả phần cũ và mọi phép đối
# chiếu số lượng thành vô nghĩa.
RUN_ID="$(date +%s)"
RAW_TOPIC="aml.smoke.raw.${RUN_ID}"
DLQ_TOPIC="aml.smoke.dlq.${RUN_ID}"
HDFS_BASE="${AML_HDFS_SMOKE_PATH:-/data/aml_smoke}/${RUN_ID}"
HDFS_URI="hdfs://namenode:8020${HDFS_BASE}"
GROUP_ID="aml-smoke-${RUN_ID}"

cleanup() {
    log "Dọn topic và thư mục của lượt chạy ${RUN_ID}"
    "${SCRIPT_DIR}/cancel_job.sh" >/dev/null 2>&1 || true
    $AML exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
        --delete --topic "$RAW_TOPIC" >/dev/null 2>&1 || true
    $AML exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
        --delete --topic "$DLQ_TOPIC" >/dev/null 2>&1 || true
    $AML exec -T namenode hdfs dfs -rm -r -f "$HDFS_BASE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

need docker

# ---------------------------------------------------------------------
group_start "1/8 Hạ tầng"
$AML up -d --wait kafka namenode datanode flink-jobmanager flink-taskmanager \
    || die "Không dựng được hạ tầng AML"
$AML up hdfs-init >/dev/null 2>&1 || true
ok "Kafka, HDFS và Flink đều xanh"
group_end

# ---------------------------------------------------------------------
group_start "2/8 Topic Kafka"
$AML run --rm -e AML_RAW_TOPIC="$RAW_TOPIC" -e AML_DLQ_TOPIC="$DLQ_TOPIC" kafka-init >/dev/null \
    || die "Không tạo được topic"
ok "Đã tạo ${RAW_TOPIC} và ${DLQ_TOPIC}"
group_end

# ---------------------------------------------------------------------
group_start "3/8 Dọn chỗ cho lượt chạy này"
$AML exec -T namenode hdfs dfs -mkdir -p "${HDFS_BASE}" >/dev/null
$AML exec -T namenode hdfs dfs -chmod -R 777 "${HDFS_BASE}" >/dev/null
ok "HDFS ${HDFS_BASE} sẵn sàng"
group_end

# ---------------------------------------------------------------------
group_start "4/8 Nộp job Flink"
"${SCRIPT_DIR}/cancel_job.sh" >/dev/null 2>&1 || true
sleep 3
# Chu kỳ chốt file rút ngắn cho phép thử. Mặc định của hệ thống là 30 giây
# cho checkpoint và 2 phút khoảng lặng cho file JSON — hợp lý khi chạy thật,
# nhưng sẽ khiến kiểm tra khói phải chờ vài phút chỉ để nhìn thấy một dòng
# lỗi được chốt xuống đĩa.
AML_JOB_JAR=/opt/flink/usrlib/aml-ingestion.jar "${SCRIPT_DIR}/submit_job.sh" \
    --aml.hdfs.base.path "$HDFS_URI" \
    --aml.raw.topic "$RAW_TOPIC" \
    --aml.group.id "$GROUP_ID" \
    --aml.checkpoint.interval.ms 10000 \
    --aml.rollover.interval.ms 15000 \
    --aml.rollover.inactivity.ms 10000 \
    --aml.offset.reset earliest \
    || die "Không nộp được job Flink"
group_end

# ---------------------------------------------------------------------
group_start "5/8 Producer đọc file mẫu và gửi vào Kafka"
producer_log="$(mktemp)"
AML_DATASET_DIR="$FIXTURE_DIR" AML_DATASET_FILE="$FIXTURE_FILE" \
    $AML run --rm \
    -e AML_RAW_TOPIC="$RAW_TOPIC" \
    -e AML_DLQ_TOPIC="$DLQ_TOPIC" \
    -e AML_CHECKPOINT_PATH="/app/data/aml/smoke-${RUN_ID}.json" \
    -e AML_RESUME=false \
    aml-producer --max-records 1000 2>&1 | tee "$producer_log"

producer_rc=${PIPESTATUS[0]}
[ "$producer_rc" -eq 0 ] || die "Producer thoát với mã ${producer_rc}"

metrics_line="$(grep -o 'rows_read=.*' "$producer_log" | tail -1)"
[ -n "$metrics_line" ] || die "Producer không in ra dòng số liệu nào"

value_of() { echo "$metrics_line" | tr ' ' '\n' | grep "^$1=" | cut -d= -f2; }
rows_read=$(value_of rows_read)
events_valid=$(value_of events_valid)
events_invalid=$(value_of events_invalid)
events_acked=$(value_of events_acked)
events_failed=$(value_of events_failed)
dlq_sent=$(value_of dlq_sent)

log "đọc=${rows_read} hợp lệ=${events_valid} lỗi=${events_invalid} đã xác nhận=${events_acked} thất bại=${events_failed} dlq=${dlq_sent}"

[ "$rows_read" -eq $((EXPECTED_VALID + EXPECTED_INVALID)) ] \
    || die "Đọc ${rows_read} dòng, mong đợi $((EXPECTED_VALID + EXPECTED_INVALID))"
[ "$events_valid" -eq "$EXPECTED_VALID" ] || die "Hợp lệ ${events_valid}, mong đợi ${EXPECTED_VALID}"
[ "$events_invalid" -eq "$EXPECTED_INVALID" ] || die "Lỗi ${events_invalid}, mong đợi ${EXPECTED_INVALID}"
[ "$events_failed" -eq 0 ] || die "${events_failed} sự kiện không gửi được"
[ "$rows_read" -eq $((events_valid + events_invalid)) ] \
    || die "Đẳng thức đối chiếu sai: đọc ≠ hợp lệ + lỗi"
[ "$events_valid" -eq "$events_acked" ] || die "Gửi ${events_valid} nhưng Kafka chỉ xác nhận ${events_acked}"
[ "$dlq_sent" -eq "$EXPECTED_INVALID" ] || die "DLQ nhận ${dlq_sent}, mong đợi ${EXPECTED_INVALID}"
ok "Producer: ${rows_read} dòng = ${events_valid} hợp lệ + ${events_invalid} lỗi, không mất bản ghi nào"
group_end

# ---------------------------------------------------------------------
group_start "6/8 Một message hỏng đi vào nhánh bị từ chối của Flink"
# Producer đã chặn dòng hỏng từ phía CSV, nên nếu chỉ có nó thì nhánh
# rejected của Flink không bao giờ được chứng minh là hoạt động. Đẩy thẳng
# một message rác vào topic để bắt Flink phải xử lý nó.
echo '{"transaction_id":"không-phải-hex","schema_version":"1.0"}' \
    | $AML exec -T kafka /opt/kafka/bin/kafka-console-producer.sh \
        --bootstrap-server localhost:9092 --topic "$RAW_TOPIC" >/dev/null 2>&1 \
    || die "Không đẩy được message hỏng vào ${RAW_TOPIC}"
ok "Đã đẩy 1 message hỏng"
group_end

# ---------------------------------------------------------------------
group_start "7/8 Kafka đã nhận đúng số message"
kafka_count() {
    $AML exec -T kafka /opt/kafka/bin/kafka-get-offsets.sh \
        --bootstrap-server localhost:9092 --topic "$1" \
        | awk -F: '{ total += $3 } END { print total + 0 }'
}
raw_count=$(kafka_count "$RAW_TOPIC")
dlq_count=$(kafka_count "$DLQ_TOPIC")
log "${RAW_TOPIC}=${raw_count} message, ${DLQ_TOPIC}=${dlq_count} message"
[ "$raw_count" -eq $((EXPECTED_VALID + 1)) ] \
    || die "Topic dữ liệu có ${raw_count} message, mong đợi đúng $((EXPECTED_VALID + 1))"
[ "$dlq_count" -eq "$EXPECTED_INVALID" ] \
    || die "DLQ có ${dlq_count} message, mong đợi đúng ${EXPECTED_INVALID}"
ok "Sự kiện đã có mặt trong Kafka"
group_end

# ---------------------------------------------------------------------
group_start "8/8 Flink ghi xuống HDFS, đọc lại và đối chiếu"
# Giữ lại đúng các dòng `khoá=giá trị` của công cụ; phần còn lại là log của
# thư viện Parquet và Hadoop, không nói thêm điều gì ở đây.
inspect() {
    $AML exec -T flink-jobmanager bash -c \
        "java -cp '/opt/flink/usrlib/aml-ingestion.jar:'\$(cat /opt/hadoop-classpath.txt) \
         vn.fin07.aml.ingest.tools.OutputInspector '$1' ${2:-0} 2>/dev/null" \
        | grep -E '^[a-z][a-z0-9_]*=' || true
}

# File chỉ được chốt sau checkpoint, mà checkpoint đặt 10 giây một lần —
# nên chờ ở đây là chờ có điều kiện, không phải sleep mù.
log "Chờ Flink chốt file (checkpoint 10 giây một lần)"
records=0
for attempt in $(seq 1 30); do
    output="$(inspect "${HDFS_URI}/bronze/transactions" 1 || true)"
    records="$(echo "$output" | grep '^records=' | cut -d= -f2 || echo 0)"
    records="${records:-0}"
    if [ "$records" -ge "$EXPECTED_VALID" ]; then
        break
    fi
    sleep 5
done

echo "$output" | sed 's/^/  /'

[ "$records" -eq "$EXPECTED_VALID" ] \
    || die "HDFS có ${records} bản ghi, mong đợi ${EXPECTED_VALID}"

distinct="$(echo "$output" | grep '^distinct_transaction_ids=' | cut -d= -f2)"
[ "$distinct" -eq "$EXPECTED_VALID" ] \
    || die "${records} bản ghi nhưng chỉ có ${distinct} transaction_id khác nhau — có trùng lặp"

label_one="$(echo "$output" | grep '^laundering_label_1=' | cut -d= -f2)"
[ "$label_one" -gt 0 ] || die "Không bản ghi nào có nhãn is_laundering=1 — nhãn đã bị mất hoặc bị lọc"

leading_zero="$(echo "$output" | grep '^banks_with_leading_zero=' | cut -d= -f2)"
[ "$leading_zero" -gt 0 ] \
    || die "Không mã ngân hàng nào còn số 0 ở đầu — định danh đã bị ép sang số ở đâu đó"

partitions="$(echo "$output" | grep '^partitions=' | cut -d= -f2)"
[ "$partitions" -gt 1 ] || die "Chỉ có ${partitions} phân vùng — dữ liệu không được chia theo ngày/giờ"

ok "HDFS: ${records} bản ghi, ${distinct} mã khác nhau, ${label_one} nhãn 1, ${partitions} phân vùng"

log "Chờ bản ghi bị từ chối"
rejected=0
for attempt in $(seq 1 20); do
    rejected_out="$(inspect "${HDFS_URI}/rejected/transactions" || true)"
    rejected="$(echo "$rejected_out" | grep '^records=' | cut -d= -f2 || echo 0)"
    rejected="${rejected:-0}"
    if [ "$rejected" -ge 1 ]; then
        break
    fi
    sleep 5
done
[ "$rejected" -ge 1 ] || die "Message hỏng không xuất hiện ở vùng rejected — nó đã bị nuốt"
ok "Vùng rejected có ${rejected} bản ghi"

log "Tổng kết: vào ${rows_read} dòng CSV + 1 message hỏng"
log "          → ${events_valid} vào Kafka → ${records} trên HDFS"
log "          → ${events_invalid} vào DLQ + ${rejected} vào rejected"
group_end

ok "Kiểm tra khói luồng nạp AML đạt toàn bộ"
