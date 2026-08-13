"""Hợp đồng dữ liệu phải tự kiểm chứng được, nếu không nó chỉ là JSON chết.

Ba thứ được kiểm ở đây:

1. Mọi file `*.schema.json` là JSON Schema draft 2020-12 hợp lệ.
2. Mọi `$ref` phân giải được — không có tham chiếu treo tới một `$defs`
   không tồn tại hay một file đã đổi tên.
3. Mọi ví dụ trong `examples/` khớp đúng schema nó khai báo, VÀ các ví dụ
   `*-invalid.json` thật sự bị từ chối. Một contract chưa từng từ chối cái gì
   thì chưa chứng minh được nó chặn được gì.

Điểm 2 quan trọng hơn vẻ ngoài của nó: `$ref` treo không làm JSON hỏng, không
làm test khác đỏ, và chỉ lộ ra vào lúc ai đó thật sự validate một payload
production.
"""

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema", reason="cài bằng: pip install -r requirements-dev.txt")

from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"

SCHEMA_FILES = sorted(CONTRACTS.rglob("*.schema.json"))
EXAMPLE_FILES = sorted(CONTRACTS.rglob("examples/*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    """Gom mọi schema cục bộ vào một registry để `$ref` giữa các file phân giải được.

    Không có bước này, jsonschema sẽ cố tải `https://fin07.local/...` qua mạng
    và test vừa chậm vừa phụ thuộc vào việc có Internet — hai thứ không được
    phép có trong một bộ kiểm thử đơn vị.
    """
    registry = Registry()
    for path in SCHEMA_FILES:
        schema = _load(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


REGISTRY = _registry()


def test_there_are_contracts_to_check() -> None:
    """Chống trường hợp test xanh vì không tìm thấy file nào."""
    assert len(SCHEMA_FILES) >= 20, f"Chỉ tìm thấy {len(SCHEMA_FILES)} schema — đường dẫn có đúng không?"


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_schema_is_valid_draft_2020_12(path: Path) -> None:
    schema = _load(path)
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_schema_declares_id_and_title(path: Path) -> None:
    schema = _load(path)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
        f"{path.name} phải khai báo draft 2020-12."
    )
    assert "$id" in schema, f"{path.name} thiếu `$id` — không có nó thì `$ref` từ file khác không trỏ tới được."
    assert "title" in schema, f"{path.name} thiếu `title`."
    assert "description" in schema, (
        f"{path.name} thiếu `description`. Contract không giải thích được nó dùng để làm gì thì người "
        f"đọc sẽ đoán, và họ sẽ đoán sai."
    )


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_all_refs_resolve(path: Path) -> None:
    """Mọi `$ref` phải phân giải được, kể cả ref chéo file."""
    schema = _load(path)
    validator = Draft202012Validator(schema, registry=REGISTRY)

    # Cách đáng tin duy nhất để buộc mọi $ref được phân giải là validate thật
    # một payload. Dùng payload rỗng: nó sẽ trượt vì thiếu trường bắt buộc,
    # nhưng chính lúc trượt là lúc mọi nhánh $ref bị đụng tới. Ref treo sẽ ném
    # `Unresolvable` chứ không phải `ValidationError`.
    list(validator.iter_errors({}))


def _schema_for_example(path: Path) -> Path:
    """Tìm schema mà một ví dụ nhắm tới.

    Quy ước chính: `<area>/examples/<tên-schema>.valid.json` ghép với
    `<area>/<tên-schema>.schema.json`. Cần quy ước theo tên vì `events/` có
    hơn chục schema — đoán theo thư mục sẽ không phân biệt được.

    Dự phòng: nếu thư mục cha chỉ có đúng một schema thì dùng nó. Đây là
    đường dành cho `ingestion/`, vốn có tên file ví dụ đặt từ trước.
    """
    stem = path.stem
    for marker in (".valid", ".invalid"):
        if stem.endswith(marker):
            candidate = path.parent.parent / f"{stem[: -len(marker)]}.schema.json"
            if candidate.exists():
                return candidate

    # Hai ví dụ ingestion đời đầu dùng hậu tố `-valid/-invalid` thay vì
    # quy ước `.valid/.invalid`. Khi ingestion có schema thứ hai, fallback
    # "thư mục chỉ có một schema" không còn xác định được nữa.
    for marker in ("-valid", "-invalid"):
        if stem.endswith(marker):
            candidate = path.parent.parent / f"{stem[: -len(marker)]}-v1.schema.json"
            if candidate.exists():
                return candidate

    schemas_in_area = sorted(path.parent.parent.glob("*.schema.json"))
    assert len(schemas_in_area) == 1, (
        f"Không xác định được schema cho ví dụ {path.name}: thư mục cha có {len(schemas_in_area)} schema. "
        f"Đặt tên ví dụ theo dạng `<tên-schema>.valid.json` hoặc `<tên-schema>.invalid.json`."
    )
    return schemas_in_area[0]


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_example_matches_its_schema(path: Path) -> None:
    """Ví dụ hợp lệ phải qua; ví dụ chứa `invalid` trong tên phải trượt."""
    validator = Draft202012Validator(_load(_schema_for_example(path)), registry=REGISTRY)
    errors = list(validator.iter_errors(_load(path)))

    if "invalid" in path.stem:
        assert errors, (
            f"{path.name} lẽ ra phải bị contract từ chối nhưng lại qua được. Ví dụ sai mà validate "
            f"thành công nghĩa là contract đang lỏng hơn ta tưởng."
        )
    else:
        assert not errors, f"{path.name} không khớp schema: {[e.message for e in errors][:3]}"
