#!/usr/bin/env bash
# Tạo topic cho luồng nạp AML. Chạy lại bao nhiêu lần cũng an toàn.
#
# Chạy bên trong container Kafka (dịch vụ `kafka-init` của compose gọi file
# này), hoặc từ máy chủ nếu có sẵn bộ công cụ Kafka:
#
#   KAFKA_BOOTSTRAP_SERVERS=localhost:29092 ./scripts/aml/create_topics.sh
#
# Số partition và hệ số nhân bản đều lấy từ biến môi trường. Trên máy cá
# nhân chỉ có một broker, nên hệ số nhân bản là 1 — ghi cứng 3 như tài liệu
# production hay khuyên sẽ làm mọi lệnh tạo topic thất bại ở đây.

set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
RAW_TOPIC="${AML_RAW_TOPIC:-aml.transactions.raw.v1}"
DLQ_TOPIC="${AML_DLQ_TOPIC:-aml.transactions.dlq.v1}"
# Detection plane (IF / rules / graph → fusion). Key = entity_id.
DETECTION_RESULT_TOPIC="${AML_DETECTION_RESULT_TOPIC:-aml.detection.result.v1}"
PARTITIONS="${AML_TOPIC_PARTITIONS:-3}"
REPLICATION="${AML_TOPIC_REPLICATION_FACTOR:-1}"
RETENTION_MS="${AML_TOPIC_RETENTION_MS:-604800000}"

KAFKA_BIN="${KAFKA_BIN:-/opt/kafka/bin}"
TOPICS_CMD="${KAFKA_BIN}/kafka-topics.sh"

if [ ! -x "$TOPICS_CMD" ]; then
    echo "Không thấy $TOPICS_CMD. Chạy script này trong container Kafka, hoặc đặt KAFKA_BIN." >&2
    exit 1
fi

# Broker có thể chưa sẵn sàng ngay cả khi cổng đã mở. Hỏi tới khi nó trả lời
# được một yêu cầu metadata thật, tối đa 60 giây.
echo "Chờ Kafka tại ${BOOTSTRAP}"
for attempt in $(seq 1 30); do
    if "$TOPICS_CMD" --bootstrap-server "$BOOTSTRAP" --list >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "Kafka không trả lời sau 60 giây" >&2
        exit 1
    fi
    sleep 2
done

create_topic() {
    local topic="$1"
    local partitions="$2"
    echo "→ ${topic} (partitions=${partitions}, replication=${REPLICATION})"
    "$TOPICS_CMD" --bootstrap-server "$BOOTSTRAP" \
        --create --if-not-exists \
        --topic "$topic" \
        --partitions "$partitions" \
        --replication-factor "$REPLICATION" \
        --config "retention.ms=${RETENTION_MS}" \
        --config compression.type=producer
}

create_topic "$RAW_TOPIC" "$PARTITIONS"
# DLQ nhận rất ít dữ liệu; một partition là đủ và giữ được thứ tự lỗi.
create_topic "$DLQ_TOPIC" "${AML_DLQ_TOPIC_PARTITIONS:-1}"
# Kết quả từng detector (kể cả không vượt ngưỡng) — đầu vào score fusion.
create_topic "$DETECTION_RESULT_TOPIC" "$PARTITIONS"

echo
echo "Topic hiện có:"
"$TOPICS_CMD" --bootstrap-server "$BOOTSTRAP" --list | sed 's/^/  /'
echo
"$TOPICS_CMD" --bootstrap-server "$BOOTSTRAP" --describe --topic "$RAW_TOPIC"
