#!/usr/bin/env bash
# Hàm dùng chung cho mọi script trong ci/.
# Không chạy trực tiếp file này; các script khác `source` nó.

set -euo pipefail

# --- In ra ------------------------------------------------------------

_ts() { date -u '+%H:%M:%S'; }

log()  { printf '\033[0;36m[%s]\033[0m %s\n' "$(_ts)" "$*" >&2; }
ok()   { printf '\033[0;32m[%s] ✓\033[0m %s\n' "$(_ts)" "$*" >&2; }
warn() { printf '\033[0;33m[%s] !\033[0m %s\n' "$(_ts)" "$*" >&2; }
die()  { printf '\033[0;31m[%s] ✗\033[0m %s\n' "$(_ts)" "$*" >&2; exit 1; }

# Nhóm log để đọc được trên cả Jenkins lẫn GitHub Actions.
group_start() {
    if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::group::$1"; else log "── $1"; fi
}
group_end() {
    if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::endgroup::"; fi
}

# --- Ngữ cảnh repo ----------------------------------------------------

repo_root() {
    git rev-parse --show-toplevel 2>/dev/null || die "Không ở trong git repository"
}

# Tag ảnh theo commit. Cùng một hàm cho mọi hệ thống CI, nên tag mà Jenkins
# đẩy lên và tag mà GitHub Actions đẩy lên không thể lệch quy ước.
image_tag() {
    echo "sha-$(git -C "$(repo_root)" rev-parse HEAD)"
}

registry() {
    echo "${REGISTRY:-ghcr.io}"
}

# Tên image, viết thường vì registry không chấp nhận chữ hoa.
image_name() {
    local component="$1"   # app | web
    local repo="${IMAGE_REPO:-${GITHUB_REPOSITORY:-fin07/local}}"
    echo "$(registry)/$(echo "$repo" | tr '[:upper:]' '[:lower:]')/${component}"
}

# --- Kiểm tra công cụ -------------------------------------------------

need() {
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || die "Thiếu công cụ: $tool"
    done
}

# --- Chờ có điều kiện, không chờ mù ------------------------------------

# retry <số lần> <giây nghỉ> <lệnh...>
retry() {
    local attempts="$1" delay="$2"; shift 2
    local n=1
    until "$@"; do
        if [ "$n" -ge "$attempts" ]; then
            return 1
        fi
        n=$((n + 1))
        sleep "$delay"
    done
    return 0
}
