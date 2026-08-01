"""Lược đồ sự kiện chuẩn hoá (canonical) phiên bản 1.0.

Một dòng CSV hợp lệ trở thành đúng một sự kiện JSON theo lược đồ này. Hợp
đồng dữ liệu bản máy đọc được nằm ở `schemas/aml-transaction-v1.schema.json`;
hai nơi phải khớp nhau và `tests/test_aml/test_schema.py` kiểm tra điều đó.

Ba quy tắc định hình mọi thứ trong file này:

1. **Định danh là chuỗi.** Mã ngân hàng `015768` mất số 0 đầu là một mã
   khác. Số tài khoản `8149656B0` không phải số. Không ép kiểu số ở bất kỳ
   đâu trong đường đi của định danh.
2. **Số tiền là `Decimal` khi tính toán.** Chỉ đổi sang số JSON ở bước ghi
   cuối cùng, và chỉ khi giá trị đó quay ngược lại đúng bằng chính nó.
3. **`transaction_id` phải tất định.** Chạy lại cùng một file cho ra cùng
   một tập mã. Không dùng UUID ngẫu nhiên, vì downstream cần khử trùng lặp
   sau khi producer khởi động lại.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

SCHEMA_VERSION = "1.0"

# 128 bit của SHA-256 là quá đủ để không đụng độ trên hàng trăm triệu giao
# dịch, và ngắn hơn một nửa so với giữ nguyên 64 ký tự hex.
TRANSACTION_ID_LENGTH = 32

# Ký tự phân tách đơn vị (US, 0x1f) không xuất hiện trong dữ liệu CSV, nên
# ghép các trường bằng nó thì không có hai bộ giá trị khác nhau nào cho ra
# cùng một chuỗi băm.
_FIELD_SEPARATOR = "\x1f"


def compute_transaction_id(
    *,
    source_file: str,
    source_line_number: int,
    timestamp_raw: str,
    from_bank: str,
    from_account: str,
    to_bank: str,
    to_account: str,
    amount_received_raw: str,
    amount_paid_raw: str,
) -> str:
    """Mã giao dịch tất định, băm từ chính nội dung dòng nguồn.

    Dùng giá trị **thô** như đọc được từ CSV chứ không dùng giá trị đã chuẩn
    hoá: chuẩn hoá là mã nguồn có thể đổi, còn nội dung file thì không. Nhờ
    vậy nâng cấp logic chuẩn hoá không làm đổi mã của dữ liệu đã nạp.
    """
    material = _FIELD_SEPARATOR.join(
        (
            source_file,
            str(source_line_number),
            timestamp_raw,
            from_bank,
            from_account,
            to_bank,
            to_account,
            amount_received_raw,
            amount_paid_raw,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return digest[:TRANSACTION_ID_LENGTH]


def to_json_number(value: Decimal) -> float:
    """Đổi `Decimal` sang số JSON, chỉ khi không mất mát.

    JSON không có kiểu thập phân. Đổi sang `float` là an toàn khi số đó quay
    ngược về đúng giá trị cũ — đúng với mọi giá trị dưới 15 chữ số có nghĩa,
    tức toàn bộ bộ dữ liệu IBM AML. Số vượt ngưỡng đó thì ném lỗi thay vì
    lặng lẽ ghi ra một con số sai khác.
    """
    as_float = float(value)
    if Decimal(repr(as_float)) != value:
        raise ValueError(
            f"Số tiền {value} không biểu diễn được chính xác bằng số JSON "
            f"(quay ngược lại thành {Decimal(repr(as_float))})"
        )
    return as_float


@dataclass(frozen=True, slots=True)
class AmlTransactionEvent:
    """Một giao dịch sau chuẩn hoá, tương ứng đúng một dòng CSV."""

    transaction_id: str
    event_time: str  # ISO-8601 không múi giờ, đúng như trong file nguồn
    event_time_epoch_ms: int
    from_bank: str
    from_account: str
    to_bank: str
    to_account: str
    amount_received: Decimal
    receiving_currency: str
    amount_paid: Decimal
    payment_currency: str
    payment_format: str
    is_laundering: int
    source_dataset: str
    source_file: str
    source_line_number: int
    ingested_at: str
    schema_version: str = SCHEMA_VERSION

    @property
    def kafka_key(self) -> str:
        """Khoá message: `from_bank:from_account`.

        Cùng một tài khoản gửi luôn vào cùng một partition, nên thứ tự các
        giao dịch của tài khoản đó được giữ *trong phạm vi partition đó*.
        Kafka không bảo đảm thứ tự giữa các partition, và luồng này không
        dựa vào một bảo đảm như vậy.
        """
        return f"{self.from_bank}:{self.from_account}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "event_time": self.event_time,
            "event_time_epoch_ms": self.event_time_epoch_ms,
            "from_bank": self.from_bank,
            "from_account": self.from_account,
            "to_bank": self.to_bank,
            "to_account": self.to_account,
            "amount_received": to_json_number(self.amount_received),
            "receiving_currency": self.receiving_currency,
            "amount_paid": to_json_number(self.amount_paid),
            "payment_currency": self.payment_currency,
            "payment_format": self.payment_format,
            "is_laundering": self.is_laundering,
            "source_dataset": self.source_dataset,
            "source_file": self.source_file,
            "source_line_number": self.source_line_number,
            "ingested_at": self.ingested_at,
            "schema_version": self.schema_version,
        }

    def to_json_bytes(self) -> bytes:
        # separators bỏ khoảng trắng thừa: trên trăm triệu message thì vài
        # byte mỗi message là hàng trăm megabyte đường truyền.
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class RejectedRow:
    """Một dòng không qua được kiểm tra, kèm đủ thông tin để truy ngược."""

    error_type: str
    error_message: str
    source_dataset: str
    source_file: str
    source_line_number: int
    raw_row: str
    rejected_at: str
    stage: str = "producer"
    schema_version: str = SCHEMA_VERSION

    @property
    def kafka_key(self) -> str:
        return f"{self.source_file}:{self.source_line_number}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "source_dataset": self.source_dataset,
            "source_file": self.source_file,
            "source_line_number": self.source_line_number,
            "raw_row": self.raw_row,
            "rejected_at": self.rejected_at,
            "stage": self.stage,
            "schema_version": self.schema_version,
        }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def utc_now_iso() -> str:
    """Thời điểm hiện tại theo UTC, dạng ISO-8601 có hậu tố `Z`."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
