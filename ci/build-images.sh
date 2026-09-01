#!/usr/bin/env bash
# Build image api/worker và image web, gắn tag theo commit.
#
#   ./ci/build-images.sh            # chỉ build
#   PUSH=true ./ci/build-images.sh  # build rồi đẩy lên registry
#
# Biến điều khiển:
#   REGISTRY     mặc định ghcr.io
#   IMAGE_REPO   ví dụ ai20k-build-phase-cohort-3/p-022
#   MOVING_TAG   tag di động thêm vào, ví dụ develop hoặc pr-42
#   PUSH         true để đẩy lên registry

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

cd "$(repo_root)"

need docker

TAG="$(image_tag)"
APP_IMAGE="$(image_name app)"
WEB_IMAGE="$(image_name web)"
PUSH="${PUSH:-false}"

build_one() {
    local name="$1" context="$2" dockerfile="$3" title="$4"
    local args=(
        build
        --file "$dockerfile"
        --tag "${name}:${TAG}"
        --label "org.opencontainers.image.revision=$(git rev-parse HEAD)"
        --label "org.opencontainers.image.title=${title}"
        --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    )
    [ -n "${MOVING_TAG:-}" ] && args+=(--tag "${name}:${MOVING_TAG}")
    args+=("$context")

    group_start "Build ${name}:${TAG}"
    docker "${args[@]}" || die "Build ${name} thất bại"
    group_end

    if [ "$PUSH" = "true" ]; then
        group_start "Đẩy ${name}"
        docker push "${name}:${TAG}" || die "Đẩy ${name}:${TAG} thất bại"
        [ -n "${MOVING_TAG:-}" ] && docker push "${name}:${MOVING_TAG}"
        group_end
    fi
}

build_one "$APP_IMAGE" . Dockerfile "FIN-07 API và worker"
build_one "$WEB_IMAGE" ./web ./web/Dockerfile "FIN-07 AML Console"

# Ghi ra file để bước triển khai dùng lại đúng tag vừa build, thay vì tự
# dựng lại chuỗi tag và có cơ hội dựng sai.
cat > .image-tags <<EOF
APP_IMAGE=${APP_IMAGE}:${TAG}
WEB_IMAGE=${WEB_IMAGE}:${TAG}
IMAGE_TAG=${TAG}
EOF

ok "Đã build ${APP_IMAGE}:${TAG} và ${WEB_IMAGE}:${TAG}"
[ "$PUSH" = "true" ] && ok "Đã đẩy lên $(registry)"
exit 0
