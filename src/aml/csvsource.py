"""Đọc file CSV giao dịch theo dòng, không nạp cả file vào bộ nhớ.

Bộ dữ liệu lớn nhất của IBM (`HI-Large_Trans.csv`) có hàng trăm triệu dòng
và nặng hàng chục gigabyte. Mọi thứ ở đây là generator; bộ nhớ mà tiến trình
dùng không phụ thuộc vào kích thước file.

Điểm khó duy nhất của file nguồn: **hai cột đều tên `Account`**.

    Timestamp,From Bank,Account,To Bank,Account,Amount Received,...
                         ^^^^^^^          ^^^^^^^

`pandas` sẽ đổi tên chúng thành `Account` và `Account.1`, `csv.DictReader`
thì giữ lại đúng một cột và **âm thầm vứt cột kia**. Cả hai đều là hành vi
của thư viện, có thể đổi giữa các phiên bản, và không phải thứ đáng đem ra
làm chỗ dựa cho một luồng dữ liệu. Ở đây các cột được đọc theo **vị trí**:
cột 2 là `from_account`, cột 4 là `to_account`, hết.
"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# Thứ tự cột của file `*_Trans.csv` trong bộ IBM AML. Vị trí là hợp đồng,
# tên chỉ để kiểm tra rằng file đưa vào đúng là file mong đợi.
EXPECTED_HEADER: tuple[str, ...] = (
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
)

COLUMN_COUNT = len(EXPECTED_HEADER)

# Chỉ số cột, đặt tên để không có con số trần nào nằm rải rác trong mã.
COL_TIMESTAMP = 0
COL_FROM_BANK = 1
COL_FROM_ACCOUNT = 2
COL_TO_BANK = 3
COL_TO_ACCOUNT = 4
COL_AMOUNT_RECEIVED = 5
COL_RECEIVING_CURRENCY = 6
COL_AMOUNT_PAID = 7
COL_PAYMENT_CURRENCY = 8
COL_PAYMENT_FORMAT = 9
COL_IS_LAUNDERING = 10


class HeaderMismatchError(RuntimeError):
    """File đưa vào không phải file giao dịch của bộ IBM AML."""


@dataclass(frozen=True, slots=True)
class SourceRow:
    """Một dòng dữ liệu thô kèm vị trí của nó trong file.

    `line_number` là số dòng vật lý trong file, đếm từ 1 và tính cả dòng tiêu
    đề. Dòng dữ liệu đầu tiên vì vậy là dòng 2 — đúng như trong ví dụ của
    hợp đồng lược đồ. Giữ đúng số dòng file là điều kiện để truy ngược một
    bản ghi ở HDFS về đúng dòng đã sinh ra nó.
    """

    line_number: int
    values: list[str]
    raw: str
    byte_length: int


class _LineTap:
    """Đọc xuyên qua một file, giữ lại nguyên văn các dòng vừa đọc.

    `csv.reader` lấy dòng từ iterator này. Một bản ghi CSV có thể trải trên
    nhiều dòng vật lý (khi có xuống dòng trong dấu nháy), nên phải chặn ở
    đúng chỗ này mới lấy được nguyên văn bản ghi để đưa vào DLQ.
    """

    def __init__(self, handle: IO[str]) -> None:
        self._handle = handle
        self.captured: list[str] = []
        self.line_number = 0

    def __iter__(self) -> "_LineTap":
        return self

    def __next__(self) -> str:
        line = next(self._handle)
        self.line_number += 1
        self.captured.append(line)
        return line

    def take(self) -> tuple[str, int]:
        """Lấy nguyên văn bản ghi vừa đọc và xoá bộ đệm."""
        raw = "".join(self.captured)
        self.captured.clear()
        return raw.rstrip("\r\n"), len(raw.encode("utf-8"))

    def first_line_of_record(self, lines_consumed: int) -> int:
        return self.line_number - lines_consumed + 1


def validate_header(header: list[str]) -> None:
    """Kiểm tra tiêu đề khớp bộ IBM AML.

    So khớp không phân biệt hoa thường và bỏ khoảng trắng thừa, vì các bản
    tải về từ Kaggle đôi khi khác nhau ở chỗ đó. Lệch số cột hoặc lệch tên
    thì dừng ngay: đây là lỗi cấu hình, không phải dòng dữ liệu hỏng, và một
    lỗi cấu hình mà chạy tiếp thì sẽ nạp sai toàn bộ file.
    """
    normalised = [column.strip().lower() for column in header]
    expected = [column.lower() for column in EXPECTED_HEADER]
    if normalised != expected:
        raise HeaderMismatchError(
            "Tiêu đề CSV không khớp lược đồ bộ IBM AML.\n"
            f"  mong đợi: {', '.join(EXPECTED_HEADER)}\n"
            f"  đọc được: {', '.join(header)}"
        )


def iter_rows(
    path: Path,
    *,
    start_line: int = 0,
    end_line: int = 0,
    encoding: str = "utf-8",
) -> Iterator[SourceRow]:
    """Sinh từng dòng dữ liệu của file CSV.

    `start_line` và `end_line` tính theo số dòng vật lý của file (dòng tiêu
    đề là 1), bao gồm cả hai đầu. `0` nghĩa là không giới hạn. Dòng nằm
    ngoài khoảng được bỏ qua **trước** khi phân tích nội dung, nên giới hạn
    phạm vi cũng là cách chạy thử nhanh trên file lớn.

    Dòng hỏng không dừng vòng lặp: nó được trả về với `values` rỗng để bước
    chuyển đổi phía sau đẩy vào DLQ.
    """
    with path.open("r", encoding=encoding, newline="") as handle:
        tap = _LineTap(handle)
        reader = csv.reader(tap)

        try:
            header = next(reader)
        except StopIteration:
            raise HeaderMismatchError(f"File rỗng: {path}") from None
        tap.take()
        validate_header(header)

        while True:
            line_before = tap.line_number
            try:
                values = next(reader)
            except StopIteration:
                return
            except csv.Error as exc:
                raw, size = tap.take()
                yield SourceRow(line_number=line_before + 1, values=[], raw=raw or str(exc), byte_length=size)
                continue

            raw, size = tap.take()
            line_number = line_before + 1
            if not values:  # dòng trống ở cuối file
                continue
            if start_line and line_number < start_line:
                continue
            if end_line and line_number > end_line:
                return
            yield SourceRow(line_number=line_number, values=values, raw=raw, byte_length=size)
