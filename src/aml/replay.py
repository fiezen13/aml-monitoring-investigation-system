"""Vòng lặp phát lại CSV vào Kafka, và cách tính nhịp phát.

Hai chế độ:

`max-throughput`
    Đọc và gửi nhanh nhất có thể. Không có `sleep` nào; tốc độ bị chặn bởi
    backpressure của hàng đợi producer chứ không bởi đồng hồ.

`event-time`
    Phát lại theo khoảng cách thời gian thật giữa các giao dịch, chia cho
    `REPLAY_SPEED_MULTIPLIER`. Dùng khi cần một dòng sự kiện trông giống
    lưu lượng thật để quan sát watermark và cửa sổ thời gian ở phía Flink.
"""

import logging
import signal
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

from src.aml import csvsource
from src.aml.checkpoint import AckTracker, Checkpoint, CheckpointStore
from src.aml.config import AmlSettings
from src.aml.csvsource import SourceRow
from src.aml.metrics import ProducerMetrics, ProgressReporter
from src.aml.schema import utc_now_iso
from src.aml.sink import EventSink
from src.aml.transform import RowRejectedError, to_event, to_rejected

logger = logging.getLogger("fin07.aml.replay")


class ReplayPacer:
    """Tính thời gian chờ giữa hai sự kiện ở chế độ `event-time`.

    Neo vào sự kiện đầu tiên thay vì cộng dồn khoảng cách từng cặp. Cộng dồn
    thì mỗi lần chờ hụt một chút sẽ tích lại thành trôi hàng phút sau một
    triệu sự kiện; neo cố định thì sai số không tích luỹ.

    Dữ liệu không được sắp xếp hoàn toàn theo thời gian là chuyện bình
    thường, và khi gặp một sự kiện có thời gian sớm hơn sự kiện trước, hàm
    này trả về 0 chứ không trả về số âm.
    """

    def __init__(self, *, enabled: bool, multiplier: float, max_sleep_seconds: float) -> None:
        self.enabled = enabled and multiplier > 0
        self._multiplier = multiplier
        self._max_sleep = max_sleep_seconds
        self._first_event_ms: int | None = None
        self._wall_start = 0.0

    def seconds_to_wait(self, event_time_epoch_ms: int, *, now: float | None = None) -> float:
        if not self.enabled:
            return 0.0
        current = time.monotonic() if now is None else now
        if self._first_event_ms is None:
            self._first_event_ms = event_time_epoch_ms
            self._wall_start = current
            return 0.0
        elapsed_dataset = (event_time_epoch_ms - self._first_event_ms) / 1000.0
        target = self._wall_start + elapsed_dataset / self._multiplier
        return max(0.0, min(target - current, self._max_sleep))


class ReplayRunner:
    """Chạy một lượt phát lại từ file CSV sang Kafka."""

    def __init__(
        self,
        settings: AmlSettings,
        sink: EventSink,
        *,
        metrics: ProducerMetrics | None = None,
        tracker: AckTracker | None = None,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self.settings = settings
        self.sink = sink
        self.metrics = metrics or ProducerMetrics()
        self.tracker = tracker or AckTracker()
        self.checkpoints = checkpoints or CheckpointStore(
            Path(settings.aml_checkpoint_path), enabled=settings.aml_checkpoint_enabled
        )
        self.progress = ProgressReporter(self.metrics, settings.aml_progress_every_seconds)
        self.pacer = ReplayPacer(
            enabled=settings.replay_mode == "event-time",
            multiplier=settings.replay_speed_multiplier,
            max_sleep_seconds=settings.replay_max_sleep_seconds,
        )
        self._stop = False
        self._last_checkpoint_at = time.monotonic()

    # ---- Tín hiệu dừng --------------------------------------------------

    def install_signal_handlers(self) -> None:
        """Dừng gọn khi nhận SIGINT hoặc SIGTERM.

        Không cắt ngang giữa chừng: vòng lặp thoát ở ranh giới một dòng, rồi
        `flush` và ghi điểm dừng. Ctrl-C không được biến thành mất dữ liệu.
        """
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum: int, _frame: FrameType | None) -> None:
        logger.info("Nhận tín hiệu %s — dừng sau dòng hiện tại", signal.Signals(signum).name)
        self._stop = True

    # ---- Vòng lặp chính -------------------------------------------------

    def resolve_start_line(self) -> int:
        """Dòng bắt đầu đọc: ưu tiên điểm dừng, rồi tới `START_LINE`."""
        configured = self.settings.start_line
        if not self.settings.aml_resume:
            return configured
        resumed = self.checkpoints.resume_line(self.settings.csv_path.name)
        if resumed and resumed > configured:
            logger.info("Chạy tiếp từ dòng %d theo điểm dừng %s", resumed, self.checkpoints.path)
            return resumed
        return configured

    def run(self) -> ProducerMetrics:
        settings = self.settings
        path = settings.csv_path
        if not path.exists():
            raise FileNotFoundError(
                f"Không thấy file dữ liệu {path}. Đặt file CSV của bộ IBM AML vào đó "
                f"hoặc trỏ AML_CSV_PATH sang nơi khác — xem docs/AML_INGESTION.md."
            )

        source_file = path.name
        source_dataset = settings.source_dataset
        start_line = self.resolve_start_line()
        from_dt = settings.from_datetime
        to_dt = settings.to_datetime

        logger.info(
            "Phát lại %s | bộ=%s | topic=%s | chế độ=%s | tốc độ=x%s | dòng đầu=%s | trần=%s bản ghi",
            path,
            source_dataset,
            settings.aml_raw_topic,
            settings.replay_mode,
            settings.replay_speed_multiplier,
            start_line or "đầu file",
            settings.max_records or "không",
        )

        rows: Iterable[SourceRow] = csvsource.iter_rows(path, start_line=start_line, end_line=settings.end_line)

        for row in rows:
            if self._stop:
                logger.info("Dừng theo yêu cầu ở dòng %d", row.line_number)
                break

            self.metrics.rows_read += 1
            self.metrics.bytes_read += row.byte_length
            self.metrics.current_line = row.line_number

            try:
                event = to_event(
                    row,
                    source_dataset=source_dataset,
                    source_file=source_file,
                    tz=settings.tzinfo,
                )
            except RowRejectedError as rejected:
                self.metrics.events_invalid += 1
                self.sink.send_rejected(
                    to_rejected(row, rejected, source_dataset=source_dataset, source_file=source_file)
                )
                self.sink.poll(0)
                continue

            if not _within_window(event.event_time_epoch_ms, from_dt, to_dt):
                # Nằm ngoài cửa sổ thời gian được yêu cầu: không phải dòng
                # lỗi, chỉ là không thuộc lượt chạy này. Trừ lại khỏi
                # rows_read để đẳng thức đọc = hợp lệ + lỗi vẫn đúng.
                self.metrics.rows_read -= 1
                continue

            wait = self.pacer.seconds_to_wait(event.event_time_epoch_ms)
            if wait > 0:
                # poll trong lúc chờ, để callback xác nhận vẫn được gọi.
                self.sink.poll(wait)

            self.metrics.events_valid += 1
            self.metrics.last_event_time = event.event_time
            self.sink.send_event(event)
            self.sink.poll(0)

            self._maybe_checkpoint(source_file)
            self.progress.maybe_report()

            if settings.max_records and self.metrics.events_valid >= settings.max_records:
                logger.info("Đạt trần MAX_RECORDS=%d", settings.max_records)
                break

        logger.info("Đang chờ Kafka xác nhận nốt %d message", self.tracker.in_flight)
        remaining = self.sink.flush(60.0)
        if remaining:
            logger.error("%d message không gửi được trong thời gian chờ", remaining)

        self._write_checkpoint(source_file)
        self.progress.report()
        _log_reconciliation(self.metrics)
        return self.metrics

    # ---- Điểm dừng ------------------------------------------------------

    def _maybe_checkpoint(self, source_file: str) -> None:
        now = time.monotonic()
        if now - self._last_checkpoint_at < self.settings.aml_checkpoint_interval_seconds:
            return
        self._last_checkpoint_at = now
        self._write_checkpoint(source_file)

    def _write_checkpoint(self, source_file: str) -> None:
        if not self.settings.aml_checkpoint_enabled:
            return
        self.checkpoints.save(
            Checkpoint(
                source_file=source_file,
                last_acked_line=self.tracker.safe_line,
                last_transaction_id=self.tracker.last_transaction_id,
                records_acked=self.tracker.acked,
                updated_at=utc_now_iso(),
            )
        )


def _within_window(epoch_ms: int, from_dt: datetime | None, to_dt: datetime | None) -> bool:
    if from_dt is None and to_dt is None:
        return True
    moment = datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC)
    if from_dt is not None and moment < from_dt:
        return False
    if to_dt is not None and moment > to_dt:
        return False
    return True


def _log_reconciliation(metrics: ProducerMetrics) -> None:
    """Đối chiếu số đầu vào với số đầu ra, và nói to nếu lệch.

    Một luồng nạp dữ liệu mà không đối chiếu được số lượng thì không ai
    chứng minh được là nó không đánh rơi bản ghi nào.
    """
    if metrics.rows_read != metrics.events_valid + metrics.events_invalid:
        logger.error(
            "Lệch số liệu: đọc %d ≠ hợp lệ %d + lỗi %d",
            metrics.rows_read,
            metrics.events_valid,
            metrics.events_invalid,
        )
    unaccounted = metrics.events_valid - metrics.events_acked - metrics.events_failed
    if unaccounted:
        logger.error("%d sự kiện hợp lệ không có kết quả gửi rõ ràng", unaccounted)
