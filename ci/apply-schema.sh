#!/usr/bin/env bash
# Áp lược đồ từ db/init/ vào một cơ sở dữ liệu đang chạy.
#
# Container postgres tự chạy thư mục này khi khởi tạo volume lần đầu. Script
# này dành cho những nơi không mount được thư mục đó vào container: service
# container của CI, hoặc một cơ sở dữ liệu do người khác quản lý.
#
# Dùng cùng một bộ file với docker compose — không có bản sao thứ hai của
# lược đồ để lệch nhau theo thời gian.
#
#   PGHOST=localhost PGPASSWORD=... POSTGRES_USER=fin07 POSTGRES_DB=fin07 \
#   FIN07_AGENT_DB_PASSWORD=... ./ci/apply-schema.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

cd "$(repo_root)"

need psql

: "${POSTGRES_USER:?POSTGRES_USER chưa đặt}"
: "${POSTGRES_DB:?POSTGRES_DB chưa đặt}"
: "${FIN07_AGENT_DB_PASSWORD:?FIN07_AGENT_DB_PASSWORD chưa đặt — xem docs/ENVIRONMENT.md}"

export PGHOST="${PGHOST:-localhost}"
export POSTGRES_USER POSTGRES_DB FIN07_AGENT_DB_PASSWORD

group_start "Áp lược đồ từ db/init/"
for file in db/init/*; do
    log "→ ${file}"
    case "$file" in
        *.sql) psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$file" >/dev/null ;;
        *.sh)  sh "$file" >/dev/null ;;
        *)     warn "bỏ qua ${file}" ;;
    esac
done
group_end

ok "Lược đồ đã áp xong"
