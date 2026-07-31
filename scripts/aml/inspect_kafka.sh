#!/usr/bin/env bash
# Nhìn vào Kafka: topic có gì, mỗi partition tới offset nào, và vài message.
#
#   ./scripts/aml/inspect_kafka.sh              # topic dữ liệu, 5 message
#   ./scripts/aml/inspect_kafka.sh dlq 20       # topic lỗi, 20 message
#
# Số ở cột cuối của phần "offset cuối" chính là số message đã vào topic —
# con số để đối chiếu với số dòng producer báo đã gửi.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE="${COMPOSE:-docker compose}"

WHICH="${1:-raw}"
LIMIT="${2:-5}"

case "$WHICH" in
    raw) TOPIC="${AML_RAW_TOPIC:-aml.transactions.raw.v1}" ;;
    dlq) TOPIC="${AML_DLQ_TOPIC:-aml.transactions.dlq.v1}" ;;
    *)   TOPIC="$WHICH" ;;
esac

cd "$REPO_ROOT"
kafka() { $COMPOSE --profile aml exec -T kafka "$@"; }

echo "── Mô tả topic ${TOPIC}"
kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic "$TOPIC"

echo
echo "── Offset cuối theo partition (tổng = số message trong topic)"
kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic "$TOPIC" \
    | tee /dev/stderr \
    | awk -F: '{ total += $3 } END { printf "  tổng cộng: %d message\n", total }'

echo
echo "── Nhóm consumer và độ trễ"
kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list \
    | while read -r group; do
        [ -z "$group" ] && continue
        kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
            --describe --group "$group" 2>/dev/null || true
    done

echo
echo "── ${LIMIT} message đầu tiên"
kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic "$TOPIC" --from-beginning --max-messages "$LIMIT" \
    --property print.key=true --property print.headers=true --timeout-ms 15000 2>/dev/null || true
