"""Suy ra quốc gia của ngân hàng từ tên trong bộ IBM AML.

Tách khỏi script nạp để phần quyết định — tên nào ra quốc gia nào — kiểm thử
được mà không cần cơ sở dữ liệu.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data/reference"
BANK_COUNTRY_CSV = REFERENCE_DIR / "bank_country.csv"
COUNTRY_GEO_CSV = REFERENCE_DIR / "country_geo.csv"

# "China Bank #2820" -> "China Bank"; "Acme Bancorp" giữ nguyên.
_SERIAL = re.compile(r"\s+#\d+$")

# Hai họ tên hư cấu, cả hai đều chỉ về Hoa Kỳ. Căn cứ đầy đủ ghi ở cuối
# data/reference/bank_country.csv.
_US_PLACE_FORM = re.compile(r"\bBank of\b", re.IGNORECASE)
_US_INSTITUTION_FORM = re.compile(
    r"\b(Bancorp|Credit Union|Thrift|Savings Bank|Federal Bank|Community Bank|Cooperative Bank|Trust Bank)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BankCountry:
    country_code: str | None
    country_source: str
    is_vasp: bool


def family_of(bank_name: str) -> str:
    """Bỏ số thứ tự để còn lại họ tên dùng cho tra cứu."""
    return _SERIAL.sub("", bank_name.strip())


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Đọc CSV tham chiếu, bỏ qua dòng chú thích bắt đầu bằng `#`."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if not line.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def load_country_geo() -> list[dict[str, str]]:
    return _read_csv(COUNTRY_GEO_CSV)


def load_lookup() -> dict[str, BankCountry]:
    lookup: dict[str, BankCountry] = {}
    for row in _read_csv(BANK_COUNTRY_CSV):
        family = row["bank_name_family"].strip()
        if not family:
            continue
        code = (row["country_code"] or "").strip().upper() or None
        source = row["country_source"].strip()
        if (source == "unknown") != (code is None):
            raise ValueError(f"{family}: country_source={source!r} không khớp country_code={code!r}")
        lookup[family] = BankCountry(
            country_code=code,
            country_source=source,
            is_vasp=row.get("is_vasp", "false").strip().lower() == "true",
        )
    return lookup


def _brand_of(family: str) -> str:
    """Phần thương hiệu, bỏ tiền tố `The` và hậu tố loại hình tổ chức."""
    brand = re.sub(r"^The\s+", "", family, flags=re.IGNORECASE)
    brand = _US_INSTITUTION_FORM.sub("", brand)
    brand = re.sub(r"\s+Bank$", "", brand, flags=re.IGNORECASE)
    return " ".join(brand.split()).casefold()


def resolve_all(families: Iterable[str], lookup: dict[str, BankCountry]) -> dict[str, BankCountry]:
    """Giải quyết cả tập tên cùng lúc, để suy được theo họ thương hiệu.

    `Acme Bank` không mang dấu hiệu quốc gia nào, nhưng `Acme Bancorp`,
    `Acme Credit Union` và `Acme Thrift` đều có trong cùng bộ dữ liệu và đều là
    loại hình tổ chức tín dụng của Mỹ. Suy theo họ thương hiệu bắt được nhóm này
    mà không cần một luật `\\bBank\\b` rộng đến mức nuốt luôn ngân hàng nước
    ngoài thêm vào sau này.
    """
    resolved = {family: resolve(family, lookup) for family in families}

    us_brands = {
        _brand_of(family)
        for family, decided in resolved.items()
        if decided.country_code == "US" and _US_INSTITUTION_FORM.search(family)
    }
    us_brands.discard("")

    for family, decided in resolved.items():
        if decided.country_source != "unknown" or decided.is_vasp:
            continue
        if _brand_of(family) in us_brands:
            resolved[family] = BankCountry(country_code="US", country_source="assigned", is_vasp=False)
    return resolved


def resolve(bank_name: str, lookup: dict[str, BankCountry]) -> BankCountry:
    """Quốc gia của một ngân hàng, theo thứ tự ưu tiên giảm dần về độ chắc chắn.

    Bảng tra cứu tường minh luôn thắng — kể cả khi tên trông giống mẫu Mỹ — để
    một dòng sửa tay trong file tham chiếu không bị quy tắc suy diễn ghi đè.
    """
    family = family_of(bank_name)
    explicit = lookup.get(family)
    if explicit is not None:
        return explicit
    if _US_PLACE_FORM.search(family) or _US_INSTITUTION_FORM.search(family):
        return BankCountry(country_code="US", country_source="assigned", is_vasp=False)
    return BankCountry(country_code=None, country_source="unknown", is_vasp=False)
