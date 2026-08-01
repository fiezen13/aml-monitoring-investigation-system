#!/usr/bin/env bash
# Dừng job nạp dữ liệu đang chạy.
#
#   ./scripts/aml/cancel_job.sh
#
# Huỷ job không làm mất dữ liệu đã chốt: FileSink chuyển file sang trạng
# thái hoàn tất ở mỗi checkpoint, nên phần đã checkpoint vẫn nằm nguyên trên
# HDFS. Phần ghi dở sau checkpoint cuối cùng sẽ được đọc lại từ Kafka khi
# nộp job lần sau, vì offset cũng chỉ được commit theo checkpoint.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE="${COMPOSE:-docker compose}"

cd "$REPO_ROOT"
flink() { $COMPOSE --profile aml exec -T flink-jobmanager flink "$@"; }

ids="$(flink list -r 2>/dev/null | grep 'FIN-07 AML ingestion' | awk '{print $4}' || true)"
if [ -z "$ids" ]; then
    echo "Không có job nào đang chạy."
    exit 0
fi

for id in $ids; do
    echo "→ huỷ ${id}"
    flink cancel "$id"
done
