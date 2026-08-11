#!/usr/bin/env bash
# Nộp job nạp dữ liệu lên cụm Flink và chờ tới khi nó thật sự chạy.
#
#   ./scripts/aml/submit_job.sh                       # nộp, chờ RUNNING
#   ./scripts/aml/submit_job.sh --aml.hdfs.format json
#
# Mọi tham số truyền vào script được chuyển thẳng cho job. Nếu đã có một job
# cùng tên đang chạy thì script dừng lại và nói ra, thay vì nộp thêm bản thứ
# hai ghi đè lên cùng thư mục HDFS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE="${COMPOSE:-docker compose}"
JAR="${AML_JOB_JAR:-/opt/flink/usrlib/aml-ingestion.jar}"

cd "$REPO_ROOT"
flink() { $COMPOSE --profile aml exec -T flink-jobmanager flink "$@"; }

running="$(flink list -r 2>/dev/null | grep -c 'FIN-07 AML ingestion' || true)"
if [ "${running:-0}" -gt 0 ]; then
    echo "Đã có job đang chạy:"
    flink list -r | grep 'FIN-07 AML ingestion'
    echo
    echo "Dừng nó trước nếu muốn nộp lại:  ./scripts/aml/cancel_job.sh"
    exit 1
fi

echo "── Nộp job"
flink run -d "$JAR" "$@"

echo
echo "── Chờ job chuyển sang RUNNING"
for attempt in $(seq 1 30); do
    if flink list -r 2>/dev/null | grep -q 'FIN-07 AML ingestion'; then
        flink list -r | grep 'FIN-07 AML ingestion'
        echo
        echo "Giao diện Flink: http://localhost:${AML_FLINK_UI_PORT:-8081}"
        exit 0
    fi
    sleep 2
done

echo "Job không vào trạng thái RUNNING sau 60 giây. Xem log:" >&2
echo "  $COMPOSE --profile aml logs flink-jobmanager --tail=100" >&2
exit 1
