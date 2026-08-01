"""Vòng lặp phát lại: giới hạn, định tuyến lỗi, nhịp phát, điểm dừng.

Không có Kafka nào trong file này. `RecordingSink` thay chỗ producer thật,
nên các bài kiểm thử này chạy được ở bất kỳ đâu và chạy trong vài mili giây.
"""

from pathlib import Path

from src.aml.checkpoint import AckTracker, CheckpointStore
from src.aml.config import AmlSettings, derive_source_dataset
from src.aml.metrics import ProducerMetrics
from src.aml.replay import ReplayPacer, ReplayRunner
from src.aml.schema import AmlTransactionEvent, RejectedRow


class RecordingSink:
    """Ghi lại mọi thứ được gửi, không đi ra ngoài tiến trình."""

    def __init__(self, metrics: ProducerMetrics, tracker: AckTracker) -> None:
        self.events: list[AmlTransactionEvent] = []
        self.rejected: list[RejectedRow] = []
        self._metrics = metrics
        self._tracker = tracker

    def send_event(self, event: AmlTransactionEvent) -> None:
        self.events.append(event)
        self._tracker.on_produced(event.source_line_number)
        self._tracker.on_acked(event.source_line_number, event.transaction_id)
        self._metrics.events_acked += 1

    def send_rejected(self, rejected: RejectedRow) -> None:
        self.rejected.append(rejected)
        self._metrics.dlq_sent += 1

    def poll(self, timeout: float = 0.0) -> None:
        return None

    def flush(self, timeout: float = 30.0) -> int:
        return 0

    def close(self) -> None:
        return None


def run(settings: AmlSettings) -> tuple[RecordingSink, ProducerMetrics]:
    metrics = ProducerMetrics()
    tracker = AckTracker()
    sink = RecordingSink(metrics, tracker)
    checkpoints = CheckpointStore(Path(settings.aml_checkpoint_path), enabled=settings.aml_checkpoint_enabled)
    ReplayRunner(settings, sink, metrics=metrics, tracker=tracker, checkpoints=checkpoints).run()
    return sink, metrics


def base_settings(fixture_csv: Path, tmp_path: Path, **overrides: object) -> AmlSettings:
    values: dict[str, object] = {
        "aml_csv_path": str(fixture_csv),
        "aml_checkpoint_path": str(tmp_path / "cp.json"),
        "aml_error_log_path": str(tmp_path / "errors.jsonl"),
        "aml_resume": False,
    }
    values.update(overrides)
    return AmlSettings(**values)


# ---- Giới hạn dữ liệu --------------------------------------------------


def test_max_records_stops_early(fixture_csv: Path, tmp_path: Path) -> None:
    sink, metrics = run(base_settings(fixture_csv, tmp_path, max_records=50))
    assert len(sink.events) == 50
    assert metrics.events_valid == 50


def test_line_range_limits_what_is_read(fixture_csv: Path, tmp_path: Path) -> None:
    sink, _ = run(base_settings(fixture_csv, tmp_path, start_line=10, end_line=19))
    assert [event.source_line_number for event in sink.events][0] >= 10
    assert max(event.source_line_number for event in sink.events) <= 19


def test_timestamp_window_filters_by_event_time(fixture_csv: Path, tmp_path: Path) -> None:
    sink, _ = run(base_settings(fixture_csv, tmp_path, from_timestamp="2022-09-01T01:00:00"))
    assert sink.events
    assert all(event.event_time >= "2022-09-01T01:00:00" for event in sink.events)


# ---- Định tuyến dòng lỗi -----------------------------------------------


def test_bad_rows_go_to_dlq_and_do_not_stop_the_run(fixture_csv: Path, tmp_path: Path) -> None:
    sink, metrics = run(base_settings(fixture_csv, tmp_path))
    assert metrics.events_invalid == len(sink.rejected) == 4
    assert {r.error_type for r in sink.rejected} == {
        "field_count",
        "timestamp_unparsable",
        "amount_negative",
        "label_invalid",
    }
    # Lượt chạy vẫn đi hết file dù có dòng hỏng ở giữa.
    assert metrics.events_valid == 200


def test_input_equals_valid_plus_invalid(fixture_csv: Path, tmp_path: Path) -> None:
    """Đẳng thức đối chiếu: không bản ghi nào bốc hơi."""
    _, metrics = run(base_settings(fixture_csv, tmp_path))
    assert metrics.rows_read == metrics.events_valid + metrics.events_invalid
    assert metrics.events_valid == metrics.events_acked + metrics.events_failed


def test_laundering_rows_are_produced_like_any_other(fixture_csv: Path, tmp_path: Path) -> None:
    sink, _ = run(base_settings(fixture_csv, tmp_path))
    labels = {event.is_laundering for event in sink.events}
    assert labels == {0, 1}


# ---- Điểm dừng ---------------------------------------------------------


def test_checkpoint_is_written_and_resumed(fixture_csv: Path, tmp_path: Path) -> None:
    settings = base_settings(fixture_csv, tmp_path, max_records=30)
    first_sink, _ = run(settings)
    stopped_at = max(event.source_line_number for event in first_sink.events)

    store = CheckpointStore(Path(settings.aml_checkpoint_path))
    checkpoint = store.load()
    assert checkpoint is not None
    assert checkpoint.last_acked_line == stopped_at
    assert checkpoint.source_file == fixture_csv.name

    resumed = base_settings(fixture_csv, tmp_path, aml_resume=True, max_records=10)
    second_sink, _ = run(resumed)
    assert min(event.source_line_number for event in second_sink.events) > stopped_at


def test_no_resume_starts_over(fixture_csv: Path, tmp_path: Path) -> None:
    run(base_settings(fixture_csv, tmp_path, max_records=30))
    sink, _ = run(base_settings(fixture_csv, tmp_path, max_records=5, aml_resume=False))
    assert min(event.source_line_number for event in sink.events) == 2


# ---- Nhịp phát ---------------------------------------------------------


def test_max_throughput_never_waits() -> None:
    pacer = ReplayPacer(enabled=False, multiplier=1.0, max_sleep_seconds=5.0)
    assert pacer.seconds_to_wait(1_000_000, now=0.0) == 0.0
    assert pacer.seconds_to_wait(9_999_999_999, now=0.0) == 0.0


def test_event_time_waits_the_gap_between_events() -> None:
    pacer = ReplayPacer(enabled=True, multiplier=1.0, max_sleep_seconds=600.0)
    pacer.seconds_to_wait(0, now=100.0)  # neo vào sự kiện đầu
    assert pacer.seconds_to_wait(60_000, now=100.0) == 60.0


def test_speed_multiplier_divides_the_wait() -> None:
    pacer = ReplayPacer(enabled=True, multiplier=100.0, max_sleep_seconds=600.0)
    pacer.seconds_to_wait(0, now=0.0)
    assert pacer.seconds_to_wait(60_000, now=0.0) == 0.6


def test_out_of_order_events_never_sleep_negative() -> None:
    """Dữ liệu không sắp xếp hoàn toàn theo thời gian là chuyện bình thường."""
    pacer = ReplayPacer(enabled=True, multiplier=1.0, max_sleep_seconds=600.0)
    pacer.seconds_to_wait(60_000, now=0.0)
    assert pacer.seconds_to_wait(0, now=0.0) == 0.0


def test_wait_is_capped(fixture_csv: Path) -> None:
    """Một khoảng trống dài trong dữ liệu không được làm tiến trình treo."""
    pacer = ReplayPacer(enabled=True, multiplier=1.0, max_sleep_seconds=2.0)
    pacer.seconds_to_wait(0, now=0.0)
    assert pacer.seconds_to_wait(86_400_000, now=0.0) == 2.0


def test_anchoring_does_not_drift() -> None:
    """Neo vào sự kiện đầu, không cộng dồn từng cặp — sai số không tích luỹ."""
    pacer = ReplayPacer(enabled=True, multiplier=1.0, max_sleep_seconds=600.0)
    pacer.seconds_to_wait(0, now=0.0)
    # Đồng hồ thực đã trôi 9.5s trong khi dữ liệu mới đi được 10s.
    assert pacer.seconds_to_wait(10_000, now=9.5) == 0.5


# ---- Suy ra tên bộ dữ liệu ---------------------------------------------


def test_dataset_name_is_derived_from_file_name() -> None:
    assert derive_source_dataset("HI-Small_Trans.csv") == "HI-Small"
    assert derive_source_dataset("LI-Large_Trans.csv") == "LI-Large"
    assert derive_source_dataset("bat_ky_ten_nao.csv") == "bat_ky_ten_nao"


def test_dataset_name_can_be_overridden(fixture_csv: Path, tmp_path: Path) -> None:
    settings = base_settings(fixture_csv, tmp_path, aml_source_dataset="HI-Small", max_records=1)
    sink, _ = run(settings)
    assert sink.events[0].source_dataset == "HI-Small"
