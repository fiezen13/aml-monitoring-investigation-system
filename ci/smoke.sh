#!/usr/bin/env bash
# Kiểm tra khói: hệ thống vừa triển khai có thật sự phục vụ được không.
#
#   ./ci/smoke.sh [api_url] [web_url]
#   ./ci/smoke.sh http://localhost:8000 http://localhost:5173
#
# Đây không phải kiểm tra "container còn sống". Container sống mà trả lỗi 500
# vẫn là hỏng. Từng bước dưới đây đi qua một mắt xích thật của hệ thống, và
# mắt xích cuối cùng chứng minh chuỗi API → Redis → worker → PostgreSQL thông.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

API_URL="${1:-${API_URL:-http://localhost:8000}}"
WEB_URL="${2:-${WEB_URL:-http://localhost:5173}}"

need curl jq

log "API ${API_URL}"
log "Web ${WEB_URL}"

# --- 1. Sẵn sàng phục vụ ----------------------------------------------
group_start "Readiness"
retry 30 2 curl -fsS "${API_URL}/health/ready" >/dev/null \
    || die "API không sẵn sàng sau 60 giây"
curl -fsS "${API_URL}/health/ready" | jq -e '.database == true and .redis == true' >/dev/null \
    || die "API lên nhưng chưa nối được PostgreSQL hoặc Redis"
ok "API sẵn sàng, đã nối PostgreSQL và Redis"
group_end

# --- 2. Có dữ liệu thật -------------------------------------------------
group_start "Dữ liệu"
cases=$(curl -fsS "${API_URL}/api/v1/cases")
count=$(echo "$cases" | jq 'length')
[ "$count" -gt 0 ] || die "Không có vụ việc LI-Small nào — hãy chạy pipeline Behaviour trước"
ok "${count} vụ việc trong hàng đợi"
group_end

# --- 3. NT7: điểm rủi ro không bao giờ đứng một mình ---------------------
group_start "Yếu tố đóng góp"
# Chọn một case mà state machine vẫn còn bước tự động. Một volume được giữ
# lại qua nhiều lần deploy có thể đã đưa case đầu tiên tới ChoNguoiPheDuyet;
# phụ thuộc vào thứ tự lúc đó khiến smoke test trả 409 dù hệ thống vẫn tốt.
case_id=$(echo "$cases" | jq -r \
    '[.[] | select(.state != "ChoNguoiPheDuyet" and .state != "XuatHoSo")][0].case_id // empty')
[ -n "$case_id" ] || die "Không còn vụ việc nào đủ điều kiện chạy bước điều tra tự động"
reasons=$(curl -fsS "${API_URL}/api/v1/cases/${case_id}" | jq '.reasons | length')
[ "$reasons" -ge 3 ] \
    || die "Vụ việc ${case_id} chỉ có ${reasons} yếu tố đóng góp, tối thiểu phải có ba (NT7)"
ok "Vụ việc ${case_id} có ${reasons} yếu tố đóng góp"
group_end

# --- 4. Giao diện phục vụ được -----------------------------------------
group_start "Giao diện"
curl -fsS "${WEB_URL}/healthz" >/dev/null || die "Giao diện không trả lời"
# Kiểm tra app shell ổn định thay vì một nhãn thương hiệu hiển thị. Tiêu đề
# giao diện có thể đổi hợp lệ; phần tử root mới là dấu hiệu image đang phục vụ
# đúng SPA thay vì một trang lỗi hoặc nội dung từ service khác.
curl -fsS "${WEB_URL}/" | grep -q '<div id="root"></div>' || die "Giao diện trả về nội dung lạ"
curl -fsS "${WEB_URL}/api/v1/queue" | jq -e '.depth >= 0' >/dev/null \
    || die "Giao diện không gọi được API qua proxy"
ok "Giao diện phục vụ được và gọi được API"
group_end

# --- 5. Hàng đợi thông từ API tới worker --------------------------------
group_start "Hàng đợi và worker"
curl -fsS -X POST "${API_URL}/api/v1/cases/${case_id}/investigate" \
    | jq -e '.status == "queued"' >/dev/null || die "Không đẩy được tác vụ vào hàng đợi"

retry 20 2 bash -c \
    "curl -fsS '${API_URL}/api/v1/queue' | jq -e '.depth == 0' >/dev/null" \
    || die "Worker không tiêu thụ hàng đợi trong 40 giây"

curl -fsS "${API_URL}/api/v1/queue" | jq -e '.worker_alive == true' >/dev/null \
    || die "Worker không còn ghi nhịp tim"
ok "Tác vụ đi từ API qua Redis tới worker và được xử lý"
group_end

ok "Kiểm tra khói đạt toàn bộ"
