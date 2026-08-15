#!/usr/bin/env bash
# Kiểm tra định dạng và lint. Gọi từ Jenkins, GitHub Actions, hoặc bằng tay.
#
#   ./ci/lint.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

cd "$(repo_root)"

PY="${PYTHON:-python3}"

group_start "ruff check"
$PY -m ruff check src tests scripts || die "ruff check không đạt"
ok "ruff check"
group_end

group_start "observability config"
$PY scripts/validate_observability.py || die "Cấu hình observability không hợp lệ"
ok "observability config"
group_end

group_start "ruff format --check"
$PY -m ruff format --check src tests scripts \
    || die "Mã chưa đúng định dạng. Chạy: make format"
ok "ruff format"
group_end

# Script shell cũng là hạ tầng, cũng hỏng được như mã Python.
if command -v shellcheck >/dev/null 2>&1; then
    group_start "shellcheck"
    shellcheck ci/*.sh db/init/*.sh || die "shellcheck không đạt"
    ok "shellcheck"
    group_end
else
    warn "Không có shellcheck trên máy này — bỏ qua (CI luôn có)"
fi

ok "Toàn bộ kiểm tra định dạng đều đạt"
