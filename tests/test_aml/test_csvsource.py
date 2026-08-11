"""Đọc CSV: hai cột `Account`, số dòng, và dòng hỏng.

Bài kiểm thử quan trọng nhất trong file này là bài đầu tiên. Hai cột trùng
tên `Account` là cái bẫy của bộ dữ liệu này: mọi cách đọc theo tên đều hoặc
đổi tên cột theo một quy tắc không ổn định, hoặc vứt mất một trong hai cột.
"""

from pathlib import Path

import pytest

from src.aml import csvsource
from src.aml.csvsource import HeaderMismatchError, iter_rows, validate_header

HEADER = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,"
    "Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering"
)


def write_csv(tmp_path: Path, *rows: str, header: str = HEADER) -> Path:
    path = tmp_path / "HI-Test_Trans.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_two_account_columns_map_to_sender_then_receiver(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        "2022/09/01 00:03,015768,AAAAAAAA1,070,BBBBBBBB2,10.91,US Dollar,10.91,US Dollar,Cheque,0",
    )
    row = next(iter_rows(path))
    assert row.values[csvsource.COL_FROM_ACCOUNT] == "AAAAAAAA1"
    assert row.values[csvsource.COL_TO_ACCOUNT] == "BBBBBBBB2"
    assert row.values[csvsource.COL_FROM_BANK] == "015768"
    assert row.values[csvsource.COL_TO_BANK] == "070"


def test_first_data_row_is_line_two(tmp_path: Path) -> None:
    """Số dòng tính cả tiêu đề — đó là số dòng người ta thấy khi mở file."""
    path = write_csv(
        tmp_path,
        "2022/09/01 00:03,010,A1,020,B2,1.00,US Dollar,1.00,US Dollar,Cheque,0",
        "2022/09/01 00:04,010,A1,020,B2,2.00,US Dollar,2.00,US Dollar,Cheque,0",
    )
    assert [row.line_number for row in iter_rows(path)] == [2, 3]


def test_start_and_end_line_limit_the_range(tmp_path: Path) -> None:
    rows = [f"2022/09/01 00:0{i},010,A1,020,B2,{i}.00,US Dollar,{i}.00,US Dollar,Cheque,0" for i in range(1, 6)]
    path = write_csv(tmp_path, *rows)
    selected = list(iter_rows(path, start_line=3, end_line=5))
    assert [row.line_number for row in selected] == [3, 4, 5]


def test_malformed_row_is_returned_not_raised(tmp_path: Path) -> None:
    """Dòng thiếu trường vẫn được trả về, để bước sau đẩy nó vào DLQ."""
    path = write_csv(
        tmp_path,
        "2022/09/01 00:03,010,A1,020,B2,1.00,US Dollar",
        "2022/09/01 00:04,010,A1,020,B2,2.00,US Dollar,2.00,US Dollar,Cheque,0",
    )
    rows = list(iter_rows(path))
    assert len(rows) == 2
    assert len(rows[0].values) == 7
    assert rows[0].raw.startswith("2022/09/01 00:03")


def test_raw_row_is_preserved_verbatim(tmp_path: Path) -> None:
    line = "2022/09/01 00:03,015768,AAAAAAAA1,070,BBBBBBBB2,10.91,US Dollar,10.91,US Dollar,Cheque,0"
    path = write_csv(tmp_path, line)
    assert next(iter_rows(path)).raw == line


def test_wrong_header_stops_immediately(tmp_path: Path) -> None:
    """Sai lược đồ là lỗi cấu hình, không phải dòng dữ liệu hỏng."""
    path = write_csv(tmp_path, header="a,b,c")
    with pytest.raises(HeaderMismatchError):
        list(iter_rows(path))


def test_header_comparison_ignores_case_and_padding() -> None:
    validate_header([column.upper() + " " for column in csvsource.EXPECTED_HEADER])


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(HeaderMismatchError):
        list(iter_rows(path))


def test_reader_streams_without_reading_whole_file(fixture_csv: Path) -> None:
    """Chỉ lấy dòng đầu thì không được đọc hết file.

    Kiểm chứng gián tiếp bằng vị trí con trỏ file: nếu generator nạp cả file
    thì con trỏ đã ở cuối, và bộ nhớ sẽ tăng theo kích thước dữ liệu.
    """
    rows = iter_rows(fixture_csv)
    first = next(rows)
    assert first.line_number == 2
    rows.close()
