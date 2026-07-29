#!/usr/bin/env bash
# Triển khai một môi trường, kiểm tra khói, tự quay lui nếu hỏng.
#
#   ./ci/deploy.sh staging
#   ./ci/deploy.sh prodlike
#
# Nguồn image: file .image-tags do ci/build-images.sh sinh ra, hoặc biến
# APP_IMAGE và WEB_IMAGE đặt sẵn. Không build tại chỗ — thứ chạy trên môi
# trường phải đúng là thứ đã qua kiểm thử.
#
# Máy đích: qua docker context, đặt bằng biến <ENV>_DOCKER_CONTEXT. Không đặt
# thì triển khai lên chính máy đang chạy script (dùng để thử ở máy cá nhân).
#
# Bí mật: script KHÔNG đọc bí mật từ repo. Jenkins tiêm chúng vào biến môi
# trường từ kho credentials trước khi gọi script này.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

cd "$(repo_root)"

need docker

ENVIRONMENT="${1:-}"
case "$ENVIRONMENT" in
    staging|prodlike) ;;
    *) die "Dùng: $0 <staging|prodlike>" ;;
esac

OVERLAY="deploy/docker-compose.${ENVIRONMENT}.yml"
[ -f "$OVERLAY" ] || die "Không có file ${OVERLAY}"

PROJECT="fin07-${ENVIRONMENT}"

# --- Máy đích ---------------------------------------------------------

context_var="$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')_DOCKER_CONTEXT"
target_context="${!context_var:-}"
if [ -n "$target_context" ]; then
    export DOCKER_CONTEXT="$target_context"
    log "Máy đích: docker context '${target_context}'"
else
    warn "Chưa đặt ${context_var} — triển khai lên chính máy này"
fi

# --- Image ------------------------------------------------------------

if [ -f .image-tags ]; then
    # shellcheck disable=SC1091
    source .image-tags
fi
: "${APP_IMAGE:?Chưa biết image nào để triển khai — chạy ci/build-images.sh trước}"
: "${WEB_IMAGE:?Chưa biết image nào để triển khai — chạy ci/build-images.sh trước}"
export APP_IMAGE WEB_IMAGE

log "APP_IMAGE ${APP_IMAGE}"
log "WEB_IMAGE ${WEB_IMAGE}"

compose() {
    docker compose -p "$PROJECT" -f docker-compose.yml -f "$OVERLAY" "$@"
}

# --- Ghi lại cái đang chạy, để còn quay lui ---------------------------
#
# Đọc trực tiếp từ container đang chạy trên máy đích chứ không lưu vào
# workspace của Jenkins: workspace bị xoá giữa các lượt build, còn máy đích
# thì luôn biết chính nó đang chạy image nào.

previous_image_of() {
    local service="$1" cid
    cid=$(compose ps -q "$service" 2>/dev/null | head -n1)
    [ -n "$cid" ] || return 0
    docker inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true
}

PREV_APP="$(previous_image_of api)"
PREV_WEB="$(previous_image_of web)"

if [ -n "$PREV_APP" ]; then
    log "Đang chạy: ${PREV_APP} / ${PREV_WEB:-không rõ}"
else
    log "Chưa có gì chạy trên môi trường này — đây là lần triển khai đầu tiên"
fi

rollback() {
    if [ -z "$PREV_APP" ]; then
        warn "Không có phiên bản trước để quay lui. Môi trường ${ENVIRONMENT} đang hỏng."
        warn "Xem log: docker compose -p ${PROJECT} logs --tail=100"
        return 1
    fi
    warn "Quay lui về ${PREV_APP}"
    APP_IMAGE="$PREV_APP" WEB_IMAGE="${PREV_WEB:-$WEB_IMAGE}" \
        compose up -d --wait --no-build --timeout 60 \
        || { warn "Quay lui cũng thất bại — cần người vào xử lý"; return 1; }
    ok "Đã quay lui về phiên bản trước"
    return 0
}

# --- Triển khai -------------------------------------------------------

group_start "Kéo image"
# --ignore-pull-failures để image dựng tại chỗ (thử pipeline ở máy cá nhân)
# không làm dừng ở đây. Cửa kiểm thật là `up --no-build` bên dưới: image
# không tồn tại ở cả registry lẫn máy đích thì bước đó báo lỗi rõ ràng.
compose pull --quiet --ignore-pull-failures || warn "Có image không kéo được — thử dùng bản có sẵn trên máy đích"
group_end

group_start "Triển khai ${ENVIRONMENT}"
if ! compose up -d --wait --no-build --remove-orphans --timeout 120; then
    warn "Triển khai thất bại: có dịch vụ không đạt trạng thái healthy"
    compose ps
    compose logs --tail=80 || true
    rollback
    die "Triển khai ${ENVIRONMENT} thất bại"
fi
group_end
ok "Mọi dịch vụ đã xanh"

# --- Kiểm tra khói ----------------------------------------------------
#
# Healthcheck xanh mới chỉ nói tiến trình còn sống. Bước này đi qua đường dữ
# liệu thật, và đây mới là thứ quyết định lần triển khai này được giữ hay bị
# quay lui.

api_url="${API_URL:-http://localhost:${API_PORT:-8000}}"
web_url="${WEB_URL:-http://localhost:${WEB_PORT:-5173}}"

group_start "Kiểm tra khói ${ENVIRONMENT}"
if ! "${SCRIPT_DIR}/smoke.sh" "$api_url" "$web_url"; then
    warn "Kiểm tra khói thất bại — hệ thống lên nhưng không phục vụ đúng"
    compose logs --tail=80 || true
    rollback
    die "Triển khai ${ENVIRONMENT} bị quay lui do kiểm tra khói không đạt"
fi
group_end

ok "Đã triển khai ${ENVIRONMENT}: ${APP_IMAGE}"
