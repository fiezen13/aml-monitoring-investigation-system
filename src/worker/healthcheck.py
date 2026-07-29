"""Healthcheck của container worker.

Worker không mở cổng nào nên không kiểm tra được bằng HTTP. Nó ghi nhịp
tim vào Redis kèm TTL; script này kiểm tra khoá đó còn sống không. Worker
treo hoặc mất kết nối Redis thì khoá hết hạn và container chuyển unhealthy.

Thoát 0 = khoẻ, 1 = không khoẻ.
"""

import sys

from src.services.queue import get_redis, worker_alive


def main() -> int:
    try:
        get_redis().ping()
    except Exception as exc:  # noqa: BLE001 — healthcheck phải nuốt mọi lỗi và báo trạng thái
        print(f"unhealthy: không nối được Redis: {exc}", file=sys.stderr)
        return 1

    if not worker_alive():
        print("unhealthy: nhịp tim worker đã hết hạn", file=sys.stderr)
        return 1

    print("healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
