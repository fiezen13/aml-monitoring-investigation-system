"""Bộ đếm và nhật ký tiến độ của producer.

Nguyên tắc: không log từng giao dịch ở mức INFO. Một file 180 triệu dòng mà
mỗi dòng một dòng log thì phần tốn kém nhất của tiến trình sẽ là ghi log, và
không ai đọc nổi kết quả. Thay vào đó là một dòng tổng hợp theo chu kỳ, dạng
`khoá=giá trị` để `grep` và `awk` được, và cũng đủ để một collector chuyển
thẳng thành metric khi hệ thống giám sát được dựng lên sau này.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("fin07.aml.metrics")


@dataclass
class ProducerMetrics:
    """Các con số của một lần chạy producer.

    Bất biến cần giữ: `rows_read == events_valid + events_invalid`, và
    `events_valid == events_acked + events_failed + đang chờ`. Kiểm tra khói
    dựa vào đúng hai đẳng thức này để khẳng định không có bản ghi nào bốc hơi.
    """

    rows_read: int = 0
    events_valid: int = 0
    events_invalid: int = 0
    events_acked: int = 0
    events_failed: int = 0
    dlq_sent: int = 0
    dlq_failed: int = 0
    bytes_read: int = 0
    current_line: int = 0
    last_event_time: str = ""
    started_at: float = field(default_factory=time.monotonic)
    _send_latency_sum_ms: float = 0.0
    _send_latency_count: int = 0
    _send_latency_max_ms: float = 0.0

    def observe_send_latency(self, seconds: float) -> None:
        millis = seconds * 1000.0
        self._send_latency_sum_ms += millis
        self._send_latency_count += 1
        self._send_latency_max_ms = max(self._send_latency_max_ms, millis)

    @property
    def elapsed_seconds(self) -> float:
        return max(time.monotonic() - self.started_at, 1e-9)

    @property
    def rows_per_second(self) -> float:
        return self.rows_read / self.elapsed_seconds

    @property
    def avg_send_latency_ms(self) -> float:
        if not self._send_latency_count:
            return 0.0
        return self._send_latency_sum_ms / self._send_latency_count

    def snapshot(self) -> dict[str, float | int | str]:
        return {
            "rows_read": self.rows_read,
            "events_valid": self.events_valid,
            "events_invalid": self.events_invalid,
            "events_acked": self.events_acked,
            "events_failed": self.events_failed,
            "dlq_sent": self.dlq_sent,
            "dlq_failed": self.dlq_failed,
            "rows_per_second": round(self.rows_per_second, 1),
            "bytes_read": self.bytes_read,
            "current_line": self.current_line,
            "last_event_time": self.last_event_time or "-",
            "send_latency_avg_ms": round(self.avg_send_latency_ms, 2),
            "send_latency_max_ms": round(self._send_latency_max_ms, 2),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
        }

    def format_line(self) -> str:
        return " ".join(f"{key}={value}" for key, value in self.snapshot().items())


class ProgressReporter:
    """In một dòng tiến độ mỗi `interval_seconds` giây, không dày hơn."""

    def __init__(self, metrics: ProducerMetrics, interval_seconds: float) -> None:
        self._metrics = metrics
        self._interval = interval_seconds
        self._last_report = time.monotonic()

    def maybe_report(self) -> None:
        now = time.monotonic()
        if now - self._last_report < self._interval:
            return
        self._last_report = now
        self.report()

    def report(self) -> None:
        logger.info("tiến độ %s", self._metrics.format_line())
