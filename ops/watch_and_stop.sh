#!/usr/bin/env bash
# Đợi job huấn luyện kết thúc rồi tắt máy — chạy TRÊN EC2, không cần máy lập trình.
#
#   nohup ops/watch_and_stop.sh > /dev/null 2>&1 &
#
# Vì sao cần: một seed HI-Medium mất 26-59 giờ. Nó thường kết thúc lúc không ai
# ngồi trước máy, và mỗi giờ máy nhàn rỗi mất 2,24 USD. Cảnh báo CloudWatch có
# bắt được, nhưng chỉ sau 6 giờ CPU dưới 1% — tức đã tiêu khoảng 13 USD.
#
# An toàn của `poweroff` phụ thuộc đúng một thuộc tính EC2:
#
#   instanceInitiatedShutdownBehavior = stop
#
# Đã kiểm là `stop`. Nếu ai đó đổi nó thành `terminate` thì script này sẽ XOÁ máy
# kèm toàn bộ artefact. Kiểm lại trước khi dùng ở nơi khác:
#
#   aws ec2 describe-instance-attribute --instance-id <id> \
#     --attribute instanceInitiatedShutdownBehavior
#
# Ổ EBS vẫn còn sau khi stop, nên artefact an toàn; bật máy lại là lấy được.
set -u

CONTAINER="${1:-fin07-hi-medium}"
LOG=/workspace/P-022/reports/run-watcher.log
GRACE_SECONDS="${GRACE_SECONDS:-300}"

mkdir -p "$(dirname "$LOG")"
echo "[$(date -u +%FT%TZ)] canh container $CONTAINER" >> "$LOG"

# docker wait chặn tới khi container dừng, rồi in mã thoát.
CODE=$(docker wait "$CONTAINER" 2>/dev/null || echo "unknown")

{
  echo "[$(date -u +%FT%TZ)] $CONTAINER kết thúc, mã thoát=$CODE"
  echo "--- 40 dòng log cuối ---"
  docker logs --tail 40 "$CONTAINER" 2>&1
  echo "--- artefact ---"
  find /workspace/P-022/models/mega-pna /workspace/P-022/reports/mega-pna -type f 2>/dev/null
  echo "--- sẽ tắt máy sau ${GRACE_SECONDS}s ---"
} >> "$LOG"

sync
# Cửa sổ nhỏ để người đang xem kịp huỷ:  sudo pkill -f watch_and_stop
sleep "$GRACE_SECONDS"

echo "[$(date -u +%FT%TZ)] poweroff" >> "$LOG"
sync
sudo poweroff
