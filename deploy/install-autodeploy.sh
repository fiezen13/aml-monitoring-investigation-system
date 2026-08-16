#!/usr/bin/env bash
# Cài agent triển khai lên máy chủ production. Chạy một lần, bằng sudo.
#
#   sudo bash deploy/install-autodeploy.sh
#
# Sau khi chạy, sửa /etc/fin07/autodeploy.env để điền token rồi bật hẹn giờ.

set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Cần chạy bằng sudo" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -d -m 755 /opt/fin07
install -m 755 "${HERE}/autodeploy.sh" /opt/fin07/autodeploy.sh

install -d -m 700 /etc/fin07
if [ ! -f /etc/fin07/autodeploy.env ]; then
    install -m 600 "${HERE}/autodeploy.env.example" /etc/fin07/autodeploy.env
    echo "Đã tạo /etc/fin07/autodeploy.env — sửa file này để điền GITHUB_TOKEN."
else
    echo "Giữ nguyên /etc/fin07/autodeploy.env đã có."
fi

install -m 644 "${HERE}/fin07-autodeploy.service" /etc/systemd/system/
install -m 644 "${HERE}/fin07-autodeploy.timer"   /etc/systemd/system/
systemctl daemon-reload

cat <<'MSG'

Đã cài. Ba bước còn lại:

  1. sudo nano /etc/fin07/autodeploy.env      # điền GITHUB_TOKEN
  2. sudo /opt/fin07/autodeploy.sh            # chạy thử một lượt, xem log
  3. sudo systemctl enable --now fin07-autodeploy.timer

Theo dõi:  journalctl -u fin07-autodeploy.service -f
Lịch chạy: systemctl list-timers fin07-autodeploy.timer
MSG
