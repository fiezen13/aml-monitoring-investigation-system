"""Điểm vào dòng lệnh của producer phát lại CSV.

    python -m src.aml --max-records 1000
    python -m src.aml --mode event-time --speed 100
    python -m src.aml --csv-path data/raw/ibm-aml/LI-Small_Trans.csv

Mọi tuỳ chọn đều có biến môi trường tương ứng (xem `src/aml/config.py` và
`docs/ENVIRONMENT.md`). Tham số dòng lệnh ghi đè biến môi trường, để một lần
chạy thử không phải sửa `.env`.
"""

import argparse
import logging
import sys
from pathlib import Path

from src.aml.checkpoint import AckTracker, CheckpointStore
from src.aml.config import AmlSettings
from src.aml.metrics import ProducerMetrics
from src.aml.replay import ReplayRunner
from src.aml.schema import AmlTransactionEvent, RejectedRow
from src.aml.sink import KafkaEventSink, RejectedFileWriter

logger = logging.getLogger("fin07.aml")


class DryRunSink:
    """Đích đến giả: đọc và chuẩn hoá đủ mọi bước, chỉ không gửi đi đâu cả.

    Dùng để kiểm tra một file dữ liệu mới trước khi đụng tới hạ tầng — nếu
    file sai lược đồ hay hỏng nhiều dòng thì biết ngay, không cần Kafka.
    """

    def __init__(self, metrics: ProducerMetrics, tracker: AckTracker) -> None:
        self._metrics = metrics
        self._tracker = tracker

    def send_event(self, event: AmlTransactionEvent) -> None:
        self._tracker.on_produced(event.source_line_number)
        self._tracker.on_acked(event.source_line_number, event.transaction_id)
        self._metrics.events_acked += 1

    def send_rejected(self, rejected: RejectedRow) -> None:
        self._metrics.dlq_sent += 1

    def poll(self, timeout: float = 0.0) -> None:
        return None

    def flush(self, timeout: float = 30.0) -> int:
        return 0

    def close(self) -> None:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.aml",
        description="Phát lại CSV giao dịch IBM AML vào Kafka theo lược đồ chuẩn hoá v1.0.",
    )
    parser.add_argument("--csv-path", help="Đường dẫn file *_Trans.csv (mặc định AML_CSV_PATH)")
    parser.add_argument("--source-dataset", help="Ghi đè tên bộ dữ liệu, mặc định suy ra từ tên file")
    parser.add_argument("--bootstrap-servers", help="Danh sách broker Kafka")
    parser.add_argument("--topic", help="Topic nhận sự kiện hợp lệ")
    parser.add_argument("--dlq-topic", help="Topic nhận dòng lỗi")
    parser.add_argument("--mode", choices=("max-throughput", "event-time"), help="Chế độ phát lại")
    parser.add_argument("--speed", type=float, help="Hệ số tăng tốc ở chế độ event-time")
    parser.add_argument("--max-records", type=int, help="Dừng sau bao nhiêu sự kiện hợp lệ (0 = không giới hạn)")
    parser.add_argument("--start-line", type=int, help="Dòng file bắt đầu đọc (tiêu đề là dòng 1)")
    parser.add_argument("--end-line", type=int, help="Dòng file cuối cùng được đọc")
    parser.add_argument("--from-timestamp", help="Chỉ phát sự kiện từ mốc này trở đi (ISO-8601)")
    parser.add_argument("--to-timestamp", help="Chỉ phát sự kiện tới mốc này")
    parser.add_argument("--checkpoint-path", help="File điểm dừng")
    parser.add_argument("--no-resume", action="store_true", help="Bỏ qua điểm dừng, chạy lại từ đầu")
    parser.add_argument("--no-checkpoint", action="store_true", help="Không ghi điểm dừng")
    parser.add_argument("--no-dlq", action="store_true", help="Không gửi dòng lỗi sang Kafka DLQ")
    parser.add_argument("--dry-run", action="store_true", help="Chuẩn hoá và kiểm tra, không gửi Kafka")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def settings_from_args(args: argparse.Namespace) -> AmlSettings:
    """Gộp tham số dòng lệnh lên trên biến môi trường."""
    overrides: dict[str, object] = {}
    mapping = {
        "csv_path": "aml_csv_path",
        "source_dataset": "aml_source_dataset",
        "bootstrap_servers": "kafka_bootstrap_servers",
        "topic": "aml_raw_topic",
        "dlq_topic": "aml_dlq_topic",
        "mode": "replay_mode",
        "speed": "replay_speed_multiplier",
        "max_records": "max_records",
        "start_line": "start_line",
        "end_line": "end_line",
        "from_timestamp": "from_timestamp",
        "to_timestamp": "to_timestamp",
        "checkpoint_path": "aml_checkpoint_path",
        "log_level": "aml_log_level",
    }
    for arg_name, field_name in mapping.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            overrides[field_name] = value
    if args.no_resume:
        overrides["aml_resume"] = False
    if args.no_checkpoint:
        overrides["aml_checkpoint_enabled"] = False
    if args.no_dlq:
        overrides["aml_dlq_enabled"] = False
    return AmlSettings(**overrides)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)

    logging.basicConfig(
        level=settings.aml_log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    metrics = ProducerMetrics()
    tracker = AckTracker()
    checkpoints = CheckpointStore(Path(settings.aml_checkpoint_path), enabled=settings.aml_checkpoint_enabled)

    if args.dry_run:
        logger.info("Chế độ dry-run: không gửi gì sang Kafka")
        sink = DryRunSink(metrics, tracker)
    else:
        rejected_writer = RejectedFileWriter(Path(settings.aml_error_log_path) if settings.aml_error_log_path else None)
        sink = KafkaEventSink(settings, metrics, tracker, rejected_writer=rejected_writer)

    runner = ReplayRunner(settings, sink, metrics=metrics, tracker=tracker, checkpoints=checkpoints)
    runner.install_signal_handlers()
    try:
        runner.run()
    finally:
        sink.close()

    # Mã thoát khác 0 khi có message không tới được Kafka: một lượt nạp thiếu
    # dữ liệu mà báo thành công thì CI không phát hiện được gì cả.
    if metrics.events_failed:
        logger.error("%d sự kiện không gửi được", metrics.events_failed)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
