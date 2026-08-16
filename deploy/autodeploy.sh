#!/usr/bin/env bash
# Đồng bộ production với nhánh phát hành, chỉ khi CI đã xanh.
#
#   sudo /opt/fin07/autodeploy.sh          # một lượt kiểm tra
#   sudo /opt/fin07/autodeploy.sh --force  # triển khai lại dù SHA không đổi
#
# Vì sao *kéo* chứ không *đẩy*
# ---------------------------------------------------------------------
# Cách quen thuộc là GitHub Actions ssh vào máy chủ rồi triển khai. Cách đó
# cần secret trong repo (khoá SSH hoặc service account), mà thêm secret đòi
# quyền Admin trên repo — quyền mà nhóm này không có (repo thuộc org khoá học).
#
# Nên đảo chiều: máy chủ tự hỏi GitHub "nhánh phát hành đang ở commit nào, CI
# của commit đó xanh chưa", rồi tự kéo về. Thứ duy nhất cần là một token chỉ
# đọc do *cá nhân* tạo trong phần cài đặt tài khoản — không đụng tới quyền repo.
#
# Đổi lại là độ trễ: thay đổi lên production sau tối đa một chu kỳ hẹn giờ.
#
# Hai điều kiện phải cùng đúng thì mới triển khai
# ---------------------------------------------------------------------
#   1. Commit đầu nhánh khác commit đang chạy.
#   2. Commit ấy có **ít nhất một** lượt kiểm tra, và **mọi** lượt đều thành công.
#
# Điều kiện 2 cố ý chặt: commit chưa từng chạy CI cũng bị từ chối, không chỉ
# commit CI đỏ. Nếu không, một lỗi cấu hình khiến workflow không kích hoạt sẽ
# âm thầm biến thành "triển khai mọi thứ được đẩy lên".

set -euo pipefail

CONFIG="${FIN07_AUTODEPLOY_CONFIG:-/etc/fin07/autodeploy.env}"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

_ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log()  { printf '[%s] %s\n' "$(_ts)" "$*"; }
die()  { printf '[%s] LỖI: %s\n' "$(_ts)" "$*" >&2; exit 1; }

[ -f "$CONFIG" ] || die "Thiếu file cấu hình $CONFIG (xem deploy/autodeploy.env.example)"
set -a
# shellcheck disable=SC1090  # đường dẫn cấu hình do biến môi trường quyết định
source "$CONFIG"
set +a

: "${GITHUB_REPO:?Thiếu GITHUB_REPO}"
: "${GITHUB_TOKEN:?Thiếu GITHUB_TOKEN}"
: "${DEPLOY_BRANCH:=develop}"
: "${APP_DIR:=/opt/fin07/app}"
: "${SMOKE_URL:=https://www.amlmonitoring.site}"
: "${COMPOSE_FILES:=-f docker-compose.yml -f deploy/docker-compose.vm.yml -f deploy/docker-compose.cloudsql.yml}"

STATE_DIR="$(dirname "$APP_DIR")/state"
DEPLOYED_SHA_FILE="${STATE_DIR}/deployed-sha"
mkdir -p "$STATE_DIR"

api() {
    local body status
    body="$(curl -sS --max-time 30 -w $'\n%{http_code}' \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${GITHUB_REPO}$1")" || die "Không gọi được GitHub API"
    status="${body##*$'\n'}"
    body="${body%$'\n'*}"
    case "$status" in
        200) printf '%s' "$body" ;;
        # Ba mã này gần như luôn là cùng một nguyên nhân, và thông báo mặc định
        # của GitHub ("Bad credentials", "Not Found") không nói ra điều đó.
        401) die "Token bị từ chối. Kiểm tra GITHUB_TOKEN trong ${CONFIG} — token mới tạo có thể chưa được phê duyệt cho tổ chức." ;;
        403) die "Token không đủ quyền hoặc đã vượt hạn mức gọi API. Cần quyền đọc Contents và Actions." ;;
        404) die "Không thấy ${GITHUB_REPO}$1. Với repo private, 404 thường nghĩa là token không có quyền đọc repo này chứ không phải repo không tồn tại." ;;
        *)   die "GitHub API trả về HTTP ${status}: $(printf '%s' "$body" | head -c 200)" ;;
    esac
}

compose() {
    # shellcheck disable=SC2086
    (cd "$APP_DIR" && docker compose $COMPOSE_FILES "$@")
}

# --- 1. Commit đầu nhánh ----------------------------------------------

target_sha="$(api "/commits/${DEPLOY_BRANCH}" | jq -r '.sha')"
[ -n "$target_sha" ] && [ "$target_sha" != "null" ] || die "Không đọc được commit đầu nhánh ${DEPLOY_BRANCH}"

current_sha="$(cat "$DEPLOYED_SHA_FILE" 2>/dev/null || echo "")"
if [ "$target_sha" = "$current_sha" ] && [ "$FORCE" -eq 0 ]; then
    log "Không có gì mới (${target_sha:0:8})"
    exit 0
fi

# --- 2. Cổng CI --------------------------------------------------------

checks="$(api "/commits/${target_sha}/check-runs?per_page=100")"
total="$(echo "$checks" | jq '.total_count')"
if [ "$total" -eq 0 ]; then
    log "Commit ${target_sha:0:8} chưa có lượt kiểm tra nào — chưa triển khai"
    exit 0
fi

# `completed` + `success` hoặc `skipped` là qua. Một job bị bỏ qua có chủ đích
# (ví dụ chỉ chạy trên pull request) không được tính là hỏng.
failed="$(echo "$checks" | jq -r '
    [.check_runs[]
     | select(.status != "completed" or (.conclusion | IN("success","skipped","neutral") | not))
     | "\(.name)=\(.status)/\(.conclusion // "đang chạy")"]
    | join(", ")')"
if [ -n "$failed" ]; then
    log "CI chưa đạt cho ${target_sha:0:8}: ${failed}"
    exit 0
fi
log "CI xanh (${total} lượt kiểm tra) cho ${target_sha:0:8} — bắt đầu triển khai"

# --- 3. Lấy mã nguồn ---------------------------------------------------

auth_url="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
if [ ! -d "${APP_DIR}/.git" ]; then
    log "Nhân bản lần đầu vào ${APP_DIR}"
    mkdir -p "$APP_DIR"
    git clone --no-checkout "$auth_url" "$APP_DIR"
fi
# Đặt remote ở mỗi lượt: token có hạn dùng và sẽ được thay.
git -C "$APP_DIR" remote set-url origin "$auth_url"
git -C "$APP_DIR" fetch --quiet origin "$DEPLOY_BRANCH"
git -C "$APP_DIR" checkout --quiet --force "$target_sha"
# Rác từ lần build trước không được mang sang bản mới; giữ lại file cấu hình
# chứa bí mật vì nó cố ý không nằm trong repo.
git -C "$APP_DIR" clean -qfdx -e .env -e .env.local

[ -f "${APP_DIR}/.env" ] || die "Thiếu ${APP_DIR}/.env — chép từ máy chủ cũ hoặc tạo từ .env.example"

# --- 4. Triển khai -----------------------------------------------------

log "Áp lược đồ cơ sở dữ liệu"
compose run --rm --build migrate

log "Dựng lại và khởi động dịch vụ"
compose up -d --build --force-recreate api worker web

# --- 5. Kiểm tra khói --------------------------------------------------
#
# Chạy trên **tên miền thật**, không phải localhost: đường đi qua Caddy, chứng
# chỉ TLS và nginx trong container web đều là những chỗ hỏng được, và hỏng ở đó
# thì người dùng vẫn thấy trang lỗi dù container đều xanh.

log "Kiểm tra khói trên ${SMOKE_URL}"
smoke_ok=1
for _ in $(seq 1 30); do
    if curl -fsS --max-time 20 "${SMOKE_URL}/api/v1/auth/users" >/dev/null 2>&1; then
        smoke_ok=0
        break
    fi
    sleep 5
done

if [ "$smoke_ok" -ne 0 ]; then
    log "Kiểm tra khói HỎNG — quay lui"
    if [ -n "$current_sha" ]; then
        git -C "$APP_DIR" checkout --quiet --force "$current_sha"
        compose up -d --build --force-recreate api worker web
        log "Đã quay lui về ${current_sha:0:8}"
    else
        log "Không có bản trước để quay lui về"
    fi
    exit 1
fi

echo "$target_sha" > "$DEPLOYED_SHA_FILE"
log "Đã triển khai ${target_sha:0:8} lên ${SMOKE_URL}"
