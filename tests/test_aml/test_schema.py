"""Hợp đồng dữ liệu: mã nguồn và file lược đồ phải nói cùng một chuyện.

`contracts/ingestion/aml-transaction-v1.schema.json` là thứ đội khác đọc để biết topic
chứa gì. Nếu nó lệch khỏi `src/aml/schema.py` thì nó tệ hơn là không có, vì
nó khiến người đọc tin vào một điều sai. Bài kiểm thử này giữ hai bên khớp.
"""

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.aml.csvsource import SourceRow
from src.aml.schema import SCHEMA_VERSION
from src.aml.transform import to_event

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts" / "ingestion"
SCHEMA_PATH = CONTRACTS / "aml-transaction-v1.schema.json"
VALID_EXAMPLE = CONTRACTS / "examples" / "aml-transaction-valid.json"
INVALID_EXAMPLE = CONTRACTS / "examples" / "aml-transaction-invalid.json"

jsonschema = pytest.importorskip("jsonschema", reason="cài bằng: pip install -r requirements-dev.txt")


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def build_event() -> dict:
    row = SourceRow(
        line_number=2,
        values=[
            "2022/09/01 00:03",
            "015768",
            "8149656B0",
            "015768",
            "8149656B0",
            "10.91",
            "US Dollar",
            "10.91",
            "US Dollar",
            "Reinvestment",
            "0",
        ],
        raw="",
        byte_length=0,
    )
    return to_event(
        row,
        source_dataset="HI-Small",
        source_file="HI-Small_Trans.csv",
        tz=ZoneInfo("UTC"),
    ).to_dict()


def test_schema_itself_is_valid(schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)


def test_producer_output_matches_the_contract(schema: dict) -> None:
    jsonschema.validate(instance=build_event(), schema=schema)


def test_contract_field_set_matches_producer_output(schema: dict) -> None:
    assert set(schema["properties"]) == set(build_event())
    assert set(schema["required"]) == set(build_event())


def test_valid_example_validates(schema: dict) -> None:
    jsonschema.validate(instance=json.loads(VALID_EXAMPLE.read_text(encoding="utf-8")), schema=schema)


def test_invalid_example_is_rejected(schema: dict) -> None:
    instance = json.loads(INVALID_EXAMPLE.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(instance))
    reported = {error.json_path for error in errors}
    # Bốn vi phạm mà ví dụ này cố tình mắc phải đều phải bị bắt.
    assert "$.from_bank" in reported
    assert "$.amount_paid" in reported
    assert "$.is_laundering" in reported
    assert "$.schema_version" in reported


def test_schema_version_is_pinned(schema: dict) -> None:
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert build_event()["schema_version"] == SCHEMA_VERSION


def test_json_bytes_are_compact_utf8() -> None:
    row = SourceRow(
        line_number=2,
        values=[
            "2022/09/01 00:03",
            "015768",
            "8149656B0",
            "015768",
            "8149656B0",
            "10.91",
            "US Dollar",
            "10.91",
            "US Dollar",
            "Reinvestment",
            "0",
        ],
        raw="",
        byte_length=0,
    )
    payload = to_event(row, source_dataset="HI-Small", source_file="f.csv", tz=ZoneInfo("UTC")).to_json_bytes()
    assert b", " not in payload
    assert json.loads(payload.decode("utf-8"))["from_bank"] == "015768"
