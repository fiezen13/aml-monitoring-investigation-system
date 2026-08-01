"""Điểm dừng để producer chạy tiếp sau khi bị ngắt.

Điều quan trọng nhất ở đây là **khi nào** điểm dừng được ghi: chỉ sau khi
Kafka đã xác nhận (`ack`) các message tương ứng, không phải sau khi đọc xong
dòng từ CSV. Ghi sau khi đọc thì một lần tắt máy đúng lúc sẽ để lại một
khoảng dữ liệu đã được đánh dấu là xong nhưng chưa bao giờ tới Kafka.

Ngay cả như vậy, ngữ nghĩa vẫn là **at-least-once**: khởi động lại có thể
gửi lại vài message đã tới nơi. Đây là lý do `transaction_id` phải tất định
— downstream khử trùng lặp được bằng chính khoá đó. Giai đoạn này chưa hiện
thực khử trùng lặp trong Flink; xem mục giới hạn trong README.
"""

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from src.aml.schema import SCHEMA_VERSION

logger = logging.getLogger("fin07.aml.checkpoint")


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Trạng thái đã được Kafka xác nhận tới đâu."""

    source_file: str
    last_acked_line: int
    last_transaction_id: str
    records_acked: int
    updated_at: str
    schema_version: str = SCHEMA_VERSION


class CheckpointStore:
    """Đọc và ghi điểm dừng vào một file JSON.

    Ghi theo kiểu thay thế nguyên tử (`write` vào file tạm rồi `os.replace`)
    nên không tồn tại trạng thái file bị cắt ngang: hoặc là điểm dừng cũ,
    hoặc là điểm dừng mới, không có thứ gì ở giữa.
    """

    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled

    def load(self) -> Checkpoint | None:
        if not self.enabled or not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Checkpoint(
                source_file=data["source_file"],
                last_acked_line=int(data["last_acked_line"]),
                last_transaction_id=data.get("last_transaction_id", ""),
                records_acked=int(data.get("records_acked", 0)),
                updated_at=data.get("updated_at", ""),
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except (OSError, ValueError, KeyError) as exc:
            # Điểm dừng hỏng thì chạy lại từ đầu là an toàn (at-least-once),
            # còn đoán nội dung của nó thì không. Báo to rồi bỏ qua.
            logger.warning("Điểm dừng %s không đọc được (%s) — bỏ qua và chạy từ đầu", self.path, exc)
            return None

    def save(self, checkpoint: Checkpoint) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, prefix=self.path.name, suffix=".tmp", delete=False
        )
        try:
            with handle as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(handle.name, self.path)
        except OSError:
            Path(handle.name).unlink(missing_ok=True)
            raise

    def resume_line(self, source_file: str) -> int:
        """Dòng đầu tiên cần đọc lại, hoặc 0 nếu không có điểm dừng dùng được.

        Điểm dừng của một file khác thì không dùng được: đổi bộ dữ liệu mà
        vẫn tiếp tục từ số dòng cũ sẽ bỏ qua phần đầu của file mới.
        """
        checkpoint = self.load()
        if checkpoint is None:
            return 0
        if checkpoint.source_file != source_file:
            logger.warning(
                "Điểm dừng thuộc về %s, lần chạy này là %s — bỏ qua điểm dừng",
                checkpoint.source_file,
                source_file,
            )
            return 0
        return checkpoint.last_acked_line + 1


class AckTracker:
    """Theo dõi dòng nào đã được Kafka xác nhận, để biết chốt điểm dừng ở đâu.

    Điểm dừng phải là dòng mà **mọi** dòng trước nó đều đã xác nhận. Kafka
    xác nhận không theo thứ tự (nhiều partition, nhiều batch), nên chốt theo
    dòng vừa được xác nhận gần nhất là sai: dòng 900 có thể xong trước dòng
    880, và chốt ở 900 sẽ bỏ mất 880 khi khởi động lại.

    Cách làm: giữ tập các dòng đang chờ. Mốc an toàn là `min(đang chờ) - 1`,
    hoặc dòng cao nhất đã gửi khi không còn gì đang chờ. Tập này bị chặn
    trên bởi hạn mức hàng đợi của producer nên không phình theo kích thước
    file.
    """

    def __init__(self) -> None:
        self._pending: set[int] = set()
        self._highest_produced = 0
        self.last_transaction_id = ""
        self.acked = 0

    def on_produced(self, line_number: int) -> None:
        self._pending.add(line_number)
        self._highest_produced = max(self._highest_produced, line_number)

    def on_acked(self, line_number: int, transaction_id: str) -> None:
        self._pending.discard(line_number)
        self.last_transaction_id = transaction_id
        self.acked += 1

    def on_failed(self, line_number: int) -> None:
        """Message gửi thất bại.

        Giữ nguyên nó trong tập đang chờ: điểm dừng không được vượt qua một
        dòng chưa tới được Kafka, nếu không lần chạy tiếp theo sẽ bỏ sót nó.
        """
        self._pending.add(line_number)

    @property
    def safe_line(self) -> int:
        if self._pending:
            return min(self._pending) - 1
        return self._highest_produced

    @property
    def in_flight(self) -> int:
        return len(self._pending)
