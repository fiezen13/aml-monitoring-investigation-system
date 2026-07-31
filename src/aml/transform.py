"""Chuyển một dòng CSV thành sự kiện chuẩn hoá, kèm kiểm tra hợp lệ.

Ranh giới của bước này rất hẹp và cố ý giữ hẹp: nó chỉ đổi *cách biểu diễn*
của dữ liệu, không đổi *nội dung*. Không có luật nghiệp vụ AML nào ở đây.

Cụ thể, những dòng sau đây **không** bị loại, dù thoạt nhìn có vẻ đáng ngờ:

* gửi và nhận cùng một tài khoản (bộ dữ liệu có, ví dụ giao dịch tái đầu tư);
* gửi và nhận cùng một ngân hàng;
* số tiền rất nhỏ hoặc rất lớn;
* `Is Laundering = 1`.

Nhãn `is_laundering` đi qua đây như một cột dữ liệu bình thường. Nó không
điều khiển nhánh nào, không lọc gì, không định tuyến gì.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Final
from zoneinfo import ZoneInfo

from src.aml import csvsource
from src.aml.csvsource import SourceRow
from src.aml.schema import AmlTransactionEvent, RejectedRow, compute_transaction_id, utc_now_iso

# Bộ IBM AML dùng `2022/09/01 00:20`. Các định dạng còn lại là dự phòng cho
# bản tải về đã bị Excel hay một công cụ trung gian định dạng lại.
TIMESTAMP_FORMATS: Final[tuple[str, ...]] = (
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


class RowRejectedError(Exception):
    """Dòng không qua được kiểm tra. Mang theo loại lỗi để phân loại ở DLQ."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def parse_timestamp(raw: str) -> datetime:
    """Đọc cột `Timestamp` thành datetime chưa gắn múi giờ."""
    text = raw.strip()
    if not text:
        raise RowRejectedError("timestamp_missing", "Cột Timestamp rỗng")
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise RowRejectedError("timestamp_unparsable", f"Không đọc được Timestamp {text!r}")


def parse_amount(raw: str, column: str) -> Decimal:
    """Đọc một cột số tiền thành `Decimal`.

    Dùng `Decimal` chứ không `float`: `0.1 + 0.2` bằng `0.30000000000000004`
    trong dấu phẩy động nhị phân, và một luồng dữ liệu tài chính không nên
    mang sẵn sai số ngay từ bước đọc file.
    """
    text = raw.strip()
    if not text:
        raise RowRejectedError("amount_missing", f"Cột {column} rỗng")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise RowRejectedError("amount_unparsable", f"Cột {column} không phải số: {text!r}") from None
    if not value.is_finite():
        raise RowRejectedError("amount_unparsable", f"Cột {column} không hữu hạn: {text!r}")
    if value < 0:
        raise RowRejectedError("amount_negative", f"Cột {column} âm: {text!r}")
    return value


def parse_identifier(raw: str, column: str) -> str:
    """Đọc mã ngân hàng hoặc số tài khoản.

    Trả về **chuỗi**, đã cắt khoảng trắng, không hơn. Không ép sang số:
    `015768` ép sang số rồi in lại thành `15768` là một ngân hàng khác, và
    `8149656B0` thì không ép được.
    """
    text = raw.strip()
    if not text:
        raise RowRejectedError("identifier_missing", f"Cột {column} rỗng")
    return text


def parse_label(raw: str) -> int:
    """Đọc cột `Is Laundering`. Chỉ chấp nhận `0` hoặc `1`."""
    text = raw.strip()
    if text not in ("0", "1"):
        raise RowRejectedError("label_invalid", f"Is Laundering phải là 0 hoặc 1, đọc được {text!r}")
    return int(text)


def parse_non_empty(raw: str, column: str, error_type: str) -> str:
    text = raw.strip()
    if not text:
        raise RowRejectedError(error_type, f"Cột {column} rỗng")
    return text


def to_event(
    row: SourceRow,
    *,
    source_dataset: str,
    source_file: str,
    tz: ZoneInfo,
    ingested_at: str | None = None,
) -> AmlTransactionEvent:
    """Dòng CSV → sự kiện chuẩn hoá. Ném `RowRejectedError` nếu không hợp lệ."""
    if len(row.values) != csvsource.COLUMN_COUNT:
        raise RowRejectedError(
            "field_count",
            f"Dòng có {len(row.values)} trường, lược đồ cần {csvsource.COLUMN_COUNT}",
        )

    values = row.values
    timestamp_raw = values[csvsource.COL_TIMESTAMP]
    naive_time = parse_timestamp(timestamp_raw)

    # Bộ dữ liệu không ghi múi giờ. Thay vì đoán, luồng này khai báo giả
    # định qua DATASET_TIMEZONE và ghi lại giả định đó trong tài liệu.
    epoch_ms = int(naive_time.replace(tzinfo=tz).timestamp() * 1000)

    from_bank = parse_identifier(values[csvsource.COL_FROM_BANK], "From Bank")
    from_account = parse_identifier(values[csvsource.COL_FROM_ACCOUNT], "Account (gửi)")
    to_bank = parse_identifier(values[csvsource.COL_TO_BANK], "To Bank")
    to_account = parse_identifier(values[csvsource.COL_TO_ACCOUNT], "Account (nhận)")

    amount_received_raw = values[csvsource.COL_AMOUNT_RECEIVED]
    amount_paid_raw = values[csvsource.COL_AMOUNT_PAID]
    amount_received = parse_amount(amount_received_raw, "Amount Received")
    amount_paid = parse_amount(amount_paid_raw, "Amount Paid")

    receiving_currency = parse_non_empty(
        values[csvsource.COL_RECEIVING_CURRENCY], "Receiving Currency", "currency_missing"
    )
    payment_currency = parse_non_empty(values[csvsource.COL_PAYMENT_CURRENCY], "Payment Currency", "currency_missing")
    payment_format = parse_non_empty(values[csvsource.COL_PAYMENT_FORMAT], "Payment Format", "payment_format_missing")
    is_laundering = parse_label(values[csvsource.COL_IS_LAUNDERING])

    transaction_id = compute_transaction_id(
        source_file=source_file,
        source_line_number=row.line_number,
        timestamp_raw=timestamp_raw.strip(),
        from_bank=from_bank,
        from_account=from_account,
        to_bank=to_bank,
        to_account=to_account,
        amount_received_raw=amount_received_raw.strip(),
        amount_paid_raw=amount_paid_raw.strip(),
    )

    return AmlTransactionEvent(
        transaction_id=transaction_id,
        event_time=naive_time.isoformat(timespec="seconds"),
        event_time_epoch_ms=epoch_ms,
        from_bank=from_bank,
        from_account=from_account,
        to_bank=to_bank,
        to_account=to_account,
        amount_received=amount_received,
        receiving_currency=receiving_currency,
        amount_paid=amount_paid,
        payment_currency=payment_currency,
        payment_format=payment_format,
        is_laundering=is_laundering,
        source_dataset=source_dataset,
        source_file=source_file,
        source_line_number=row.line_number,
        ingested_at=ingested_at or utc_now_iso(),
    )


def to_rejected(row: SourceRow, error: RowRejectedError, *, source_dataset: str, source_file: str) -> RejectedRow:
    """Đóng gói một dòng lỗi kèm đủ thông tin để tìm lại nó trong file nguồn."""
    return RejectedRow(
        error_type=error.error_type,
        error_message=error.message,
        source_dataset=source_dataset,
        source_file=source_file,
        source_line_number=row.line_number,
        raw_row=row.raw,
        rejected_at=utc_now_iso(),
    )
