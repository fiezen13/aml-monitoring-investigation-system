#!/usr/bin/env bash
# Tải bộ dữ liệu IBM AML từ Kaggle. **Tuỳ chọn** — không phải bước bắt buộc.
#
#   ./scripts/aml/download_dataset.sh              # tải HI-Small_Trans.csv
#   ./scripts/aml/download_dataset.sh LI-Medium_Trans.csv
#
# Luồng nạp không phụ thuộc vào script này. Ai không muốn dùng Kaggle CLI thì
# tải thủ công từ trang bộ dữ liệu rồi đặt file vào data/raw/ibm-aml/ — kết
# quả hoàn toàn như nhau.
#
#   https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
#
# Khoá Kaggle: script này đọc từ ~/.kaggle/kaggle.json hoặc từ biến môi
# trường KAGGLE_USERNAME và KAGGLE_KEY. Không có khoá nào được ghi vào repo,
# và data/raw/ nằm trong .gitignore — bộ dữ liệu nặng hàng trăm megabyte tới
# hàng chục gigabyte, không có chuyện commit nó.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DATASET_SLUG="ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
TARGET_DIR="${AML_DATASET_DIR:-${REPO_ROOT}/data/raw/ibm-aml}"
WANTED_FILE="${1:-HI-Small_Trans.csv}"

if ! command -v kaggle >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Không thấy lệnh `kaggle`.

  pip install kaggle

rồi tạo API token ở https://www.kaggle.com/settings → Create New Token,
lưu file vào ~/.kaggle/kaggle.json và `chmod 600` nó.

Hoặc bỏ qua script này: tải file từ trang bộ dữ liệu và đặt vào
data/raw/ibm-aml/ bằng tay.
EOF
    exit 1
fi

mkdir -p "$TARGET_DIR"

if [ -f "${TARGET_DIR}/${WANTED_FILE}" ]; then
    echo "Đã có ${TARGET_DIR}/${WANTED_FILE} — không tải lại."
    exit 0
fi

echo "Tải ${WANTED_FILE} từ Kaggle vào ${TARGET_DIR}"
kaggle datasets download -d "$DATASET_SLUG" -f "$WANTED_FILE" -p "$TARGET_DIR"

# Kaggle trả về file .zip cho phần lớn file lớn.
if [ -f "${TARGET_DIR}/${WANTED_FILE}.zip" ]; then
    echo "Giải nén"
    unzip -o "${TARGET_DIR}/${WANTED_FILE}.zip" -d "$TARGET_DIR"
    rm -f "${TARGET_DIR}/${WANTED_FILE}.zip"
fi

ls -lh "${TARGET_DIR}/${WANTED_FILE}"
echo
echo "Kiểm tra nhanh file vừa tải (không cần Kafka):"
echo "  python -m src.aml --csv-path ${TARGET_DIR}/${WANTED_FILE} --dry-run --max-records 1000 --no-checkpoint"
