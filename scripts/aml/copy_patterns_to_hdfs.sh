#!/usr/bin/env bash
# Chép các file *_Patterns.txt lên HDFS, nguyên trạng.
#
#   ./scripts/aml/copy_patterns_to_hdfs.sh
#
# Bộ dữ liệu IBM đi kèm các file mô tả mẫu hình giao dịch. Giai đoạn này
# **không** phân tích chúng: không parser, không luật, không mô hình. Chúng
# chỉ được đặt vào vùng dữ liệu tham chiếu trên HDFS để sau này dùng tới mà
# không phải đi tìm lại nguồn.
#
# Đích: /data/aml/reference/patterns/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE="${COMPOSE:-docker compose}"

SOURCE_DIR="${AML_DATASET_DIR:-${REPO_ROOT}/data/raw/ibm-aml}"
HDFS_DIR="${AML_HDFS_REFERENCE_DIR:-/data/aml/reference/patterns}"

shopt -s nullglob
patterns=("${SOURCE_DIR}"/*_Patterns.txt)
shopt -u nullglob

if [ ${#patterns[@]} -eq 0 ]; then
    echo "Không thấy file *_Patterns.txt nào trong ${SOURCE_DIR} — không có gì để chép." >&2
    exit 0
fi

cd "$REPO_ROOT"
$COMPOSE --profile aml exec -T namenode hdfs dfs -mkdir -p "$HDFS_DIR"

for file in "${patterns[@]}"; do
    name="$(basename "$file")"
    echo "→ ${name}"
    # Đưa qua stdin để không phải bind-mount thư mục dữ liệu vào namenode.
    $COMPOSE --profile aml exec -T namenode \
        hdfs dfs -put -f - "${HDFS_DIR}/${name}" < "$file"
done

echo
$COMPOSE --profile aml exec -T namenode hdfs dfs -ls "$HDFS_DIR"
