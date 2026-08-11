#!/usr/bin/env bash
# Nhìn vào HDFS: cây phân vùng, số file, dung lượng, và số bản ghi.
#
#   ./scripts/aml/inspect_hdfs.sh
#
# Đọc lại file Parquet cần một công cụ hiểu Parquet; script này dùng
# `parquet-tools` có sẵn trong bộ Hadoop nếu có, còn không thì báo cách đọc
# bằng Python. Với định dạng JSON Lines thì đếm dòng là đủ.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE="${COMPOSE:-docker compose}"

BASE="${AML_HDFS_INSPECT_PATH:-/data/aml}"

cd "$REPO_ROOT"
hdfs() { $COMPOSE --profile aml exec -T namenode hdfs dfs "$@"; }

echo "── Cây thư mục dưới ${BASE}"
hdfs -ls -R "$BASE" | grep -v '^Found' | sed 's/^/  /' | head -60

echo
echo "── Dung lượng"
hdfs -du -h "$BASE" | sed 's/^/  /'

echo
echo "── Phân vùng dữ liệu hợp lệ"
hdfs -ls "${BASE}/bronze/transactions" 2>/dev/null | grep -v '^Found' | awk '{print "  " $NF}' || \
    echo "  (chưa có phân vùng nào — Flink chỉ chốt file sau checkpoint đầu tiên)"

echo
echo "── File đã hoàn tất (không tính file .inprogress)"
completed=$(hdfs -ls -R "${BASE}/bronze/transactions" 2>/dev/null \
    | awk '$NF ~ /transactions-/ && $NF !~ /inprogress/ {print $NF}' || true)
if [ -z "$completed" ]; then
    echo "  chưa có"
else
    echo "$completed" | sed 's/^/  /'
    echo "  tổng: $(echo "$completed" | wc -l | tr -d ' ') file"
fi

echo
echo "── Bản ghi bị từ chối"
rejected_files="$(hdfs -ls -R "${BASE}/rejected" 2>/dev/null | awk '$NF ~ /rejected-/ && $NF !~ /inprogress/ {print $NF}')"
if [ -z "$rejected_files" ]; then
    echo "  chưa có bản ghi nào bị từ chối"
else
    echo "$rejected_files" | sed 's/^/  /'
    rejected_lines=0
    for file in $rejected_files; do
        count="$(hdfs -cat "$file" 2>/dev/null | wc -l | tr -d ' ')"
        rejected_lines=$((rejected_lines + count))
    done
    echo "  tổng số dòng bị từ chối: ${rejected_lines}"
fi

echo
echo "Đọc lại nội dung file Parquet:"
echo "  python -c \"import pandas; print(pandas.read_parquet('<file>').head())\"   # sau khi hdfs dfs -get"
