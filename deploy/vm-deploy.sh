#!/usr/bin/env bash
# Dựng hoặc cập nhật FIN-07 trên VM GCP phục vụ https://amlmonitoring.site/
#
# Chạy trên chính VM, từ thư mục gốc của repo:
#
#   bash deploy/vm-deploy.sh
#
# Chạy lại được nhiều lần: kéo code mới, dựng lại image, khởi động lại các
# dịch vụ đã đổi, rồi kiểm tra sức khoẻ. Dữ liệu trong volume giữ nguyên.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

COMPOSE_FILES=(-f docker-compose.yml -f deploy/docker-compose.vm.yml)

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mLỗi: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------
log "Kiểm tra điều kiện"

command -v docker >/dev/null || die "chưa cài docker"
docker compose version >/dev/null 2>&1 || die "chưa có docker compose v2"

[[ -f .env ]] || die ".env chưa tồn tại. Tạo từ .env.example và đặt POSTGRES_PASSWORD, FIN07_AGENT_DB_PASSWORD, ACME_EMAIL"

# Không `source .env`: dotenv không phải shell script. Ví dụ APP_NAME trong
# file mẫu chứa khoảng trắng và sẽ bị shell hiểu thành một lệnh; tệ hơn, một
# giá trị có ký tự shell có thể bị thực thi ngay trên máy production.
dotenv_value() {
    local key=$1 line value
    line=$(grep -E "^[[:space:]]*${key}=" .env | tail -n 1 || true)
    value=${line#*=}
    # Docker Compose chấp nhận giá trị được bao bằng nháy đơn hoặc nháy kép.
    # Bỏ đúng một cặp nháy ngoài để phần kiểm tra bên dưới thấy giá trị thật.
    if [[ ${#value} -ge 2 ]]; then
        if [[ ${value:0:1} == '"' && ${value: -1} == '"' ]] || \
           [[ ${value:0:1} == "'" && ${value: -1} == "'" ]]; then
            value=${value:1:${#value}-2}
        fi
    fi
    printf '%s' "$value"
}

POSTGRES_PASSWORD_VALUE=${POSTGRES_PASSWORD:-$(dotenv_value POSTGRES_PASSWORD)}
FIN07_AGENT_DB_PASSWORD_VALUE=${FIN07_AGENT_DB_PASSWORD:-$(dotenv_value FIN07_AGENT_DB_PASSWORD)}
ACME_EMAIL_VALUE=${ACME_EMAIL:-$(dotenv_value ACME_EMAIL)}
SITE_DOMAIN=${SITE_DOMAIN:-$(dotenv_value SITE_DOMAIN)}
SITE_DOMAIN=${SITE_DOMAIN:-amlmonitoring.site}
USE_CLOUD_SQL_VALUE=${USE_CLOUD_SQL:-$(dotenv_value USE_CLOUD_SQL)}
DATABASE_URL_VALUE=${DATABASE_URL:-$(dotenv_value DATABASE_URL)}

[[ -n "$FIN07_AGENT_DB_PASSWORD_VALUE" ]] || die "FIN07_AGENT_DB_PASSWORD chưa đặt trong .env"
[[ -n "$ACME_EMAIL_VALUE" ]] || die "ACME_EMAIL chưa đặt trong .env"

if [[ "$USE_CLOUD_SQL_VALUE" == "true" ]]; then
    # Cloud SQL: container postgres không dựng, nên POSTGRES_PASSWORD không
    # còn ý nghĩa. Thay vào đó DATABASE_URL trở thành thứ bắt buộc.
    COMPOSE_FILES+=(-f deploy/docker-compose.cloudsql.yml)

    [[ -n "$DATABASE_URL_VALUE" ]] \
        || die "USE_CLOUD_SQL=true nhưng DATABASE_URL chưa đặt. Lấy bằng: terraform output -raw database_url"

    # Trỏ vào host `postgres` nghĩa là chép nhầm giá trị của môi trường dev —
    # với lớp phủ Cloud SQL thì container đó không tồn tại và stack sẽ hỏng ở
    # chỗ khó hiểu. Bắt ngay tại đây.
    if [[ "$DATABASE_URL_VALUE" == *"@postgres:"* ]]; then
        die "DATABASE_URL đang trỏ vào container postgres, không phải Cloud SQL. Dùng: terraform output -raw database_url"
    fi

    # Instance đặt ssl_mode = ENCRYPTED_ONLY nên kết nối không mã hoá bị từ
    # chối, mà thông báo của libpq khi thiếu tham số này không nói rõ nguyên do.
    if [[ "$DATABASE_URL_VALUE" != *"sslmode="* ]]; then
        printf '\033[1;33mCảnh báo: DATABASE_URL thiếu ?sslmode=require — Cloud SQL sẽ từ chối kết nối.\033[0m\n'
    fi

    log "Dùng Cloud SQL (container postgres không dựng)"
else
    [[ -n "$POSTGRES_PASSWORD_VALUE" ]] || die "POSTGRES_PASSWORD chưa đặt trong .env"

    # Mật khẩu mặc định của môi trường dev không được mang lên máy có IP công cộng.
    if [[ "$POSTGRES_PASSWORD_VALUE" == "fin07_dev_password" ]]; then
        die "POSTGRES_PASSWORD vẫn là mật khẩu mặc định của môi trường dev — đổi trước khi deploy"
    fi
fi

# ---------------------------------------------------------------------
log "Kiểm tra DNS của $SITE_DOMAIN"

PUBLIC_IP=$(curl -fsS --max-time 10 -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
    2>/dev/null || curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || echo "")
DNS_IP=$(getent hosts "$SITE_DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || echo "")

if [[ -n "$PUBLIC_IP" && -n "$DNS_IP" && "$PUBLIC_IP" != "$DNS_IP" ]]; then
    # Cảnh báo chứ không dừng: dựng stack vẫn có ích, chỉ là Caddy sẽ xin
    # chứng chỉ thất bại tới khi DNS trỏ đúng.
    printf '\033[1;33mCảnh báo: %s trỏ về %s, còn máy này là %s.\n' "$SITE_DOMAIN" "$DNS_IP" "$PUBLIC_IP"
    printf 'Let'"'"'s Encrypt sẽ không cấp được chứng chỉ tới khi DNS trỏ đúng.\033[0m\n'
else
    echo "DNS: $SITE_DOMAIN → ${DNS_IP:-chưa phân giải được} (máy này: ${PUBLIC_IP:-không xác định})"
fi

# ---------------------------------------------------------------------
log "Kéo code mới nhất"
if [[ -d .git ]]; then
    git fetch --all --prune
    git checkout develop
    git pull --ff-only
    echo "HEAD: $(git log --oneline -1)"
fi

# ---------------------------------------------------------------------
log "Dựng image"
docker compose "${COMPOSE_FILES[@]}" build

log "Khởi động stack"
# --wait chờ tới khi healthcheck xanh; không có nó thì script kết thúc trước
# khi hệ thống thực sự phục vụ được và bước kiểm tra bên dưới báo lỗi giả.
docker compose "${COMPOSE_FILES[@]}" up -d --wait --remove-orphans

# ---------------------------------------------------------------------
log "Kiểm tra sức khoẻ"

docker compose "${COMPOSE_FILES[@]}" ps

echo
echo "-- API (từ trong mạng compose) --"
docker compose "${COMPOSE_FILES[@]}" exec -T api \
    python -c "import urllib.request,sys; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"

echo "-- Giao diện qua Caddy (HTTPS) --"
if curl -fsS --max-time 20 "https://$SITE_DOMAIN/healthz" >/dev/null 2>&1; then
    echo "https://$SITE_DOMAIN/healthz → ok"
else
    printf '\033[1;33mChưa gọi được qua HTTPS. Xem log Caddy:\n'
    printf '  docker compose %s logs caddy --tail 50\033[0m\n' "${COMPOSE_FILES[*]}"
fi

echo "-- API qua Caddy --"
curl -fsS --max-time 20 "https://$SITE_DOMAIN/api/v1/dashboard" 2>/dev/null \
    | head -c 200 || echo "(chưa gọi được — bình thường nếu chứng chỉ đang được cấp)"

log "Xong. Giao diện: https://$SITE_DOMAIN/"
echo "Thư mục triển khai: $ROOT"
