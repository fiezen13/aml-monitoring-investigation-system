"""Gửi sự kiện sang Kafka, và ghi dòng lỗi ra DLQ.

`confluent_kafka` được nạp **lười** trong hàm khởi tạo chứ không ở đầu file.
Nhờ vậy toàn bộ phần lõi — đọc CSV, chuẩn hoá, băm mã giao dịch, điểm dừng —
kiểm thử được trên máy không cài `librdkafka`, và các bài kiểm thử đơn vị của
gói này chạy mà không cần Kafka.

Về độ tin cậy, cấu hình mặc định chọn phía an toàn:

* `acks=all` — message chỉ được coi là xong khi mọi bản sao trong ISR đã ghi;
* `enable.idempotence=true` — một lần thử lại của librdkafka không tạo bản
  trùng trong cùng một phiên producer;
* hàng đợi nội bộ có trần — chạm trần thì producer *chờ*, đây chính là
  backpressure, thay vì phình bộ nhớ cho tới khi bị hệ điều hành giết.

Không có `Future` nào của message được giữ lại: librdkafka gọi callback khi
có kết quả, và callback chỉ cập nhật bộ đếm cùng bộ theo dõi xác nhận. Bộ
nhớ vì thế không lớn lên theo số message đã gửi.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Protocol

from src.aml.checkpoint import AckTracker
from src.aml.config import AmlSettings
from src.aml.metrics import ProducerMetrics
from src.aml.schema import SCHEMA_VERSION, AmlTransactionEvent, RejectedRow

logger = logging.getLogger("fin07.aml.sink")


class EventSink(Protocol):
    """Hợp đồng tối thiểu mà vòng lặp phát lại cần ở một đích đến."""

    def send_event(self, event: AmlTransactionEvent) -> None: ...

    def send_rejected(self, rejected: RejectedRow) -> None: ...

    def poll(self, timeout: float = 0.0) -> None: ...

    def flush(self, timeout: float = 30.0) -> int: ...

    def close(self) -> None: ...


class RejectedFileWriter:
    """Ghi dòng lỗi ra một file JSON Lines cục bộ.

    Tồn tại song song với DLQ trên Kafka có chủ ý: khi Kafka là thứ đang
    hỏng thì DLQ trên Kafka cũng hỏng theo, và file cục bộ là nơi duy nhất
    còn lại để biết dòng nào đã rớt.
    """

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._handle = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = path.open("a", encoding="utf-8")

    def write(self, rejected: RejectedRow) -> None:
        if self._handle is None:
            return
        self._handle.write(json.dumps(rejected.to_dict(), ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None


def build_producer_config(settings: AmlSettings) -> dict[str, Any]:
    """Cấu hình librdkafka. Tách riêng để kiểm thử được mà không cần Kafka."""
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "acks": "all",
        "enable.idempotence": True,
        # Với idempotence bật, librdkafka tự giữ retries ở mức tối đa và
        # max.in.flight ≤ 5; khai báo tường minh để người đọc không phải
        # tra tài liệu mới biết giá trị thực tế là gì.
        "retries": 10_000_000,
        "max.in.flight.requests.per.connection": 5,
        "compression.type": settings.kafka_compression_type,
        "linger.ms": settings.kafka_linger_ms,
        "batch.size": settings.kafka_batch_size,
        "queue.buffering.max.messages": settings.kafka_queue_buffering_max_messages,
        "message.timeout.ms": settings.kafka_message_timeout_ms,
        "client.id": "fin07-aml-csv-replay",
    }


class KafkaEventSink:
    """Đích đến Kafka thật, dùng `confluent_kafka.Producer`."""

    def __init__(
        self,
        settings: AmlSettings,
        metrics: ProducerMetrics,
        tracker: AckTracker,
        *,
        rejected_writer: RejectedFileWriter | None = None,
    ) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                "Thiếu gói confluent-kafka. Cài bằng `pip install -r requirements.txt` "
                "hoặc chạy producer trong container `aml-producer`."
            ) from exc

        self._settings = settings
        self._metrics = metrics
        self._tracker = tracker
        self._rejected_writer = rejected_writer
        self._producer = Producer(build_producer_config(settings))
        self._headers = [
            ("schema-version", SCHEMA_VERSION),
            ("source-dataset", settings.source_dataset),
            ("source-file", settings.csv_path.name),
            ("content-type", "application/json"),
        ]

    # ---- Gửi ----------------------------------------------------------

    def send_event(self, event: AmlTransactionEvent) -> None:
        self._tracker.on_produced(event.source_line_number)
        started = time.monotonic()

        def on_delivery(err: Any, msg: Any) -> None:
            self._metrics.observe_send_latency(time.monotonic() - started)
            if err is not None:
                self._metrics.events_failed += 1
                self._tracker.on_failed(event.source_line_number)
                logger.error(
                    "Gửi thất bại: dòng=%s transaction_id=%s lỗi=%s",
                    event.source_line_number,
                    event.transaction_id,
                    err,
                )
                return
            self._metrics.events_acked += 1
            self._tracker.on_acked(event.source_line_number, event.transaction_id)

        self._produce_with_backpressure(
            topic=self._settings.aml_raw_topic,
            key=event.kafka_key,
            value=event.to_json_bytes(),
            on_delivery=on_delivery,
        )

    def send_rejected(self, rejected: RejectedRow) -> None:
        if self._rejected_writer is not None:
            self._rejected_writer.write(rejected)
        if not self._settings.aml_dlq_enabled:
            return

        def on_delivery(err: Any, msg: Any) -> None:
            if err is not None:
                self._metrics.dlq_failed += 1
                logger.error("Gửi DLQ thất bại: dòng=%s lỗi=%s", rejected.source_line_number, err)
                return
            self._metrics.dlq_sent += 1

        self._produce_with_backpressure(
            topic=self._settings.aml_dlq_topic,
            key=rejected.kafka_key,
            value=rejected.to_json_bytes(),
            on_delivery=on_delivery,
        )

    def _produce_with_backpressure(self, *, topic: str, key: str, value: bytes, on_delivery: Any) -> None:
        """Đẩy một message, chờ khi hàng đợi nội bộ đầy.

        `BufferError` không phải lỗi mà là tín hiệu backpressure: hàng đợi
        đã chạm trần. Đúng việc cần làm là gọi `poll` để librdkafka giải
        phóng chỗ, rồi thử lại — chứ không phải bỏ message hay nới trần.
        """
        from confluent_kafka import KafkaException

        while True:
            try:
                self._producer.produce(
                    topic=topic,
                    key=key.encode("utf-8"),
                    value=value,
                    headers=self._headers,
                    on_delivery=on_delivery,
                )
                return
            except BufferError:
                self._producer.poll(0.5)
            except KafkaException:
                # Lỗi ở mức kết nối hoặc cấu hình: không nuốt, để vòng ngoài
                # dừng producer và báo lỗi rõ ràng.
                raise

    # ---- Vòng đời ------------------------------------------------------

    def poll(self, timeout: float = 0.0) -> None:
        self._producer.poll(timeout)

    def flush(self, timeout: float = 30.0) -> int:
        """Chờ mọi message đang chờ. Trả về số message **chưa** gửi được."""
        return int(self._producer.flush(timeout))

    def close(self) -> None:
        remaining = self.flush(self._settings.kafka_message_timeout_ms / 1000.0)
        if remaining:
            logger.error("Còn %d message chưa gửi được khi đóng producer", remaining)
        if self._rejected_writer is not None:
            self._rejected_writer.close()
