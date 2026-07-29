"""Worker xử lý tác vụ nền của FIN-07.

Vòng đời một tác vụ điều tra kéo dài hàng phút (mục tiêu ≤ 3 phút,
ARC-001 mục 5.3) nên không chạy được trong vòng đời một HTTP request.
API đẩy tác vụ vào Redis, tiến trình này lấy ra và chạy.

Phần điều phối agent LangGraph do Hiển hiện thực ở Sprint 3. Ở đây worker
đã chạy được đầu–cuối: nhận tác vụ, chuyển trạng thái vụ việc, ghi nhật ký
kiểm toán, và giữ nhịp tim cho healthcheck của container.
"""

import json
import logging
import signal
import sys
import time
from types import FrameType
from typing import Any

from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_session
from src.services.queue import get_redis

logger = logging.getLogger("fin07.worker")

_shutdown = False


def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Nhận tín hiệu %s — dừng sau khi xong tác vụ hiện tại", signal.Signals(signum).name)
    _shutdown = True


def beat() -> None:
    """Ghi nhịp tim. Healthcheck của container đọc đúng khoá này."""
    settings = get_settings()
    get_redis().set(settings.worker_heartbeat_key, str(time.time()), ex=settings.worker_heartbeat_ttl)


def handle_investigate_case(payload: dict[str, Any]) -> None:
    """Khởi động điều tra một vụ việc.

    Chuyển vụ việc sang trạng thái TruyHoiBangChung và ghi nhật ký. Không
    có nhánh nào ở đây đi thẳng tới XuatHoSo — theo máy trạng thái ở Hình 4,
    lối vào duy nhất của XuatHoSo là ChoNguoiPheDuyet (NT3).
    """
    case_id = payload["case_id"]
    with get_session() as session:
        updated = session.execute(
            text(
                """
                UPDATE aml_case
                   SET state = 'TruyHoiBangChung', updated_at = now()
                 WHERE case_id = :case_id AND state = 'TiepNhanCanhBao'
                """
            ),
            {"case_id": case_id},
        ).rowcount
        if not updated:
            logger.warning("Vụ việc %s không ở trạng thái TiepNhanCanhBao — bỏ qua", case_id)
            return
        session.execute(
            text(
                """
                INSERT INTO audit_log (case_id, event_type, actor, actor_role, payload)
                VALUES (:case_id, 'case_state_changed', 'worker', 'system', :payload)
                """
            ),
            {
                "case_id": case_id,
                "payload": json.dumps({"from": "TiepNhanCanhBao", "to": "TruyHoiBangChung"}),
            },
        )
    logger.info("Vụ việc %s chuyển sang TruyHoiBangChung", case_id)


def handle_ping(payload: dict[str, Any]) -> None:
    """Tác vụ rỗng dùng để kiểm chứng hàng đợi thông suốt."""
    logger.info("ping %s", payload)


HANDLERS = {
    "investigate_case": handle_investigate_case,
    "ping": handle_ping,
}


def process(raw: str) -> None:
    job = json.loads(raw)
    handler = HANDLERS.get(job.get("type", ""))
    if handler is None:
        logger.error("Không có handler cho tác vụ loại %r (job %s)", job.get("type"), job.get("job_id"))
        return
    started = time.monotonic()
    try:
        handler(job.get("payload", {}))
    except Exception:
        logger.exception("Tác vụ %s thất bại", job.get("job_id"))
    else:
        logger.info("Tác vụ %s xong trong %.2fs", job.get("job_id"), time.monotonic() - started)


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    client = get_redis()
    beat()
    logger.info("Worker sẵn sàng, đang nghe hàng đợi %s", settings.worker_queue)

    while not _shutdown:
        beat()
        item = client.blpop([settings.worker_queue], timeout=int(settings.worker_poll_interval))
        if item is None:
            continue
        process(item[1])

    logger.info("Worker đã dừng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
