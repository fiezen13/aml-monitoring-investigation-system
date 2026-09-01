"""Chuẩn hoá dòng CSV: định danh, thời gian, số tiền, nhãn, mã tất định."""

from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.aml.csvsource import SourceRow
from src.aml.schema import to_json_number
from src.aml.transform import RowRejectedError, to_event, to_rejected

UTC = ZoneInfo("UTC")


def row(*values: str, line_number: int = 2) -> SourceRow:
    raw = ",".join(values)
    return SourceRow(line_number=line_number, values=list(values), raw=raw, byte_length=len(raw))


def sample_row(**overrides: str) -> SourceRow:
    line_number = int(overrides.pop("_line", "2"))
    fields = {
        "timestamp": "2022/09/01 00:03",
        "from_bank": "015768",
        "from_account": "8149656B0",
        "to_bank": "015768",
        "to_account": "8149656B0",
        "amount_received": "10.91",
        "receiving_currency": "US Dollar",
        "amount_paid": "10.91",
        "payment_currency": "US Dollar",
        "payment_format": "Reinvestment",
        "is_laundering": "0",
    }
    fields.update(overrides)
    return row(*fields.values(), line_number=line_number)


def convert(source: SourceRow, tz: ZoneInfo = UTC):
    return to_event(source, source_dataset="HI-Small", source_file="HI-Small_Trans.csv", tz=tz)


# ---- Định danh ---------------------------------------------------------


def test_leading_zero_of_bank_id_survives() -> None:
    event = convert(sample_row(from_bank="015768", to_bank="000"))
    assert event.from_bank == "015768"
    assert event.to_bank == "000"


def test_hexadecimal_account_stays_a_string() -> None:
    event = convert(sample_row(from_account="8149656B0", to_account="00A1B2C30"))
    assert event.from_account == "8149656B0"
    assert event.to_account == "00A1B2C30"


def test_json_keeps_identifiers_as_strings() -> None:
    payload = convert(sample_row(from_bank="0070")).to_dict()
    assert payload["from_bank"] == "0070"
    assert isinstance(payload["from_account"], str)


# ---- Thời gian ---------------------------------------------------------


def test_timestamp_parses_dataset_format() -> None:
    event = convert(sample_row(timestamp="2022/09/01 00:03"))
    assert event.event_time == "2022-09-01T00:03:00"
    assert event.event_time_epoch_ms == 1661990580000


def test_timezone_variable_changes_epoch_not_wall_clock_text() -> None:
    """Đổi DATASET_TIMEZONE thì epoch đổi, còn chữ trong `event_time` thì không."""
    utc = convert(sample_row(timestamp="2022/09/01 00:03"))
    saigon = convert(sample_row(timestamp="2022/09/01 00:03"), tz=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert utc.event_time == saigon.event_time
    assert utc.event_time_epoch_ms - saigon.event_time_epoch_ms == 7 * 3600 * 1000


@pytest.mark.parametrize("bad", ["", "hôm qua", "2022-13-45 99:99", "01/09/2022"])
def test_unparsable_timestamp_is_rejected(bad: str) -> None:
    with pytest.raises(RowRejectedError) as excinfo:
        convert(sample_row(timestamp=bad))
    assert excinfo.value.error_type.startswith("timestamp")


# ---- Số tiền -----------------------------------------------------------


def test_amounts_are_decimal_not_float() -> None:
    event = convert(sample_row(amount_received="0.00000340", amount_paid="12345678.91"))
    assert event.amount_received == Decimal("0.00000340")
    assert event.amount_paid == Decimal("12345678.91")


def test_decimal_to_json_number_round_trips() -> None:
    for text in ("10.91", "0.00000340", "89999999.99", "0", "0.01"):
        assert Decimal(repr(to_json_number(Decimal(text)))) == Decimal(text)


def test_zero_amount_is_valid() -> None:
    assert convert(sample_row(amount_received="0", amount_paid="0")).amount_paid == Decimal("0")


@pytest.mark.parametrize("bad", ["-1.00", "abc", "", "NaN"])
def test_bad_amount_is_rejected(bad: str) -> None:
    with pytest.raises(RowRejectedError) as excinfo:
        convert(sample_row(amount_paid=bad))
    assert excinfo.value.error_type.startswith("amount")


# ---- Nhãn --------------------------------------------------------------


@pytest.mark.parametrize("label", ["0", "1"])
def test_label_accepts_zero_and_one(label: str) -> None:
    assert convert(sample_row(is_laundering=label)).is_laundering == int(label)


@pytest.mark.parametrize("label", ["", "2", "yes", "true", "-1"])
def test_label_rejects_anything_else(label: str) -> None:
    with pytest.raises(RowRejectedError) as excinfo:
        convert(sample_row(is_laundering=label))
    assert excinfo.value.error_type == "label_invalid"


# ---- Những gì KHÔNG được loại bỏ ---------------------------------------


def test_same_sender_and_receiver_is_kept() -> None:
    event = convert(sample_row(from_account="AAAA1", to_account="AAAA1", from_bank="010", to_bank="010"))
    assert event.from_account == event.to_account


def test_extreme_amounts_are_kept() -> None:
    assert convert(sample_row(amount_paid="0.00000001", amount_received="0.00000001"))
    assert convert(sample_row(amount_paid="999999999.99", amount_received="999999999.99"))


def test_laundering_label_one_is_kept_untouched() -> None:
    """Nhãn chỉ là dữ liệu. Không lọc, không định tuyến, không cảnh báo."""
    event = convert(sample_row(is_laundering="1"))
    assert event.is_laundering == 1
    assert event.to_dict()["is_laundering"] == 1


def test_currency_mismatch_is_kept() -> None:
    event = convert(sample_row(receiving_currency="US Dollar", payment_currency="Bitcoin"))
    assert event.receiving_currency != event.payment_currency


# ---- Trường thiếu ------------------------------------------------------


@pytest.mark.parametrize(
    "column,error",
    [
        ("from_bank", "identifier_missing"),
        ("from_account", "identifier_missing"),
        ("to_bank", "identifier_missing"),
        ("to_account", "identifier_missing"),
        ("receiving_currency", "currency_missing"),
        ("payment_currency", "currency_missing"),
        ("payment_format", "payment_format_missing"),
    ],
)
def test_empty_required_column_is_rejected(column: str, error: str) -> None:
    with pytest.raises(RowRejectedError) as excinfo:
        convert(sample_row(**{column: "   "}))
    assert excinfo.value.error_type == error


def test_wrong_field_count_is_rejected() -> None:
    with pytest.raises(RowRejectedError) as excinfo:
        convert(row("2022/09/01 00:03", "010", "A1"))
    assert excinfo.value.error_type == "field_count"


# ---- Mã giao dịch tất định ---------------------------------------------


def test_transaction_id_is_stable_across_runs() -> None:
    first = convert(sample_row())
    second = convert(sample_row())
    assert first.transaction_id == second.transaction_id
    assert len(first.transaction_id) == 32


def test_transaction_id_changes_with_content() -> None:
    base = convert(sample_row()).transaction_id
    assert convert(sample_row(amount_paid="10.92")).transaction_id != base
    assert convert(sample_row(to_account="OTHER1")).transaction_id != base
    assert convert(sample_row(_line="3")).transaction_id != base


def test_transaction_id_does_not_depend_on_ingest_time() -> None:
    first = to_event(sample_row(), source_dataset="HI-Small", source_file="f.csv", tz=UTC, ingested_at="A")
    second = to_event(sample_row(), source_dataset="HI-Small", source_file="f.csv", tz=UTC, ingested_at="B")
    assert first.transaction_id == second.transaction_id
    assert first.ingested_at != second.ingested_at


# ---- Định tuyến lỗi ----------------------------------------------------


def test_rejected_row_carries_enough_to_trace_back() -> None:
    source = row("2022/09/01 00:03", "010")
    try:
        convert(source)
    except RowRejectedError as exc:
        rejected = to_rejected(source, exc, source_dataset="HI-Small", source_file="HI-Small_Trans.csv")

    payload = rejected.to_dict()
    assert payload["source_file"] == "HI-Small_Trans.csv"
    assert payload["source_line_number"] == 2
    assert payload["raw_row"] == "2022/09/01 00:03,010"
    assert payload["error_type"] == "field_count"
    assert payload["error_message"]


def test_kafka_key_is_sender_bank_and_account() -> None:
    assert convert(sample_row(from_bank="015768", from_account="8149656B0")).kafka_key == "015768:8149656B0"
