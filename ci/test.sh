#!/usr/bin/env bash
# Chạy toàn bộ kiểm thử, kèm PostgreSQL và Redis thật.
#
# Hai chế độ, tự nhận biết:
#
#   * Đã có sẵn cơ sở dữ liệu (DATABASE_URL và REDIS_URL đã đặt) — dùng luôn.
#     Đây là cách GitHub Actions chạy, với service container.
#   * Chưa có gì — tự dựng postgres và redis bằng docker compose, chạy xong
#     thì dọn. Đây là cách Jenkins và máy cá nhân chạy.
#
#   ./ci/test.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

cd "$(repo_root)"

PY="${PYTHON:-python3}"
OWN_STACK=0
PROJECT=""

cleanup() {
    if [ "$OWN_STACK" = "1" ] && [ -n "$PROJECT" ]; then
        log "Dọn hạ tầng kiểm thử (${PROJECT})"
        docker compose -p "$PROJECT" -f deploy/docker-compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [ -z "${DATABASE_URL:-}" ] || [ -z "${REDIS_URL:-}" ]; then
    need docker
    OWN_STACK=1
    # Tên project riêng cho mỗi lượt chạy: hai job song song trên cùng một
    # agent Jenkins không được giẫm lên cơ sở dữ liệu của nhau.
    PROJECT="fin07test-${BUILD_NUMBER:-$$}"

    # Cổng 0 để Docker tự cấp cổng trống — tránh đụng cổng 5432 của stack
    # phát triển đang chạy trên chính máy đó.
    export TEST_PG_PORT="${TEST_PG_PORT:-0}"
    export TEST_REDIS_PORT="${TEST_REDIS_PORT:-0}"
    export POSTGRES_USER=fin07
    export POSTGRES_PASSWORD=fin07_test_password
    export POSTGRES_DB=fin07
    export FIN07_AGENT_DB_PASSWORD=fin07_agent_test_password

    group_start "Dựng PostgreSQL và Redis cho kiểm thử"
    docker compose -p "$PROJECT" -f deploy/docker-compose.test.yml up -d --wait
    pg_port=$(docker compose -p "$PROJECT" -f deploy/docker-compose.test.yml port postgres 5432 | sed 's/.*://')
    redis_port=$(docker compose -p "$PROJECT" -f deploy/docker-compose.test.yml port redis 6379 | sed 's/.*://')
    log "PostgreSQL cổng ${pg_port}, Redis cổng ${redis_port}"
    group_end

    export PGHOST=127.0.0.1
    export PGPORT="$pg_port"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    export DATABASE_URL="postgresql+psycopg://fin07:${POSTGRES_PASSWORD}@127.0.0.1:${pg_port}/fin07"
    export REDIS_URL="redis://127.0.0.1:${redis_port}/0"

    "${SCRIPT_DIR}/apply-schema.sh"
else
    log "Dùng cơ sở dữ liệu đã có sẵn"
fi

export APP_ENV=test

group_start "pytest"
$PY -m pytest --cov=src --cov-report=term-missing --cov-report=xml --junitxml=pytest-report.xml
group_end

# Job Flink là mã Java, cần JDK và Maven. Không phải agent nào cũng có, và
# bắt mọi agent phải có chỉ vì một module là quá tay — nên bước này tự bỏ
# qua khi thiếu công cụ, và nói ra rằng nó đã bỏ qua chứ không im lặng.
group_start "Kiểm thử job Flink"
if command -v mvn >/dev/null 2>&1; then
    (cd flink/aml-ingestion && mvn -B test)
    ok "Kiểm thử job Flink đạt"
else
    warn "Bỏ qua kiểm thử job Flink: máy này không có Maven"
fi
group_end

ok "Toàn bộ kiểm thử đều đạt"
