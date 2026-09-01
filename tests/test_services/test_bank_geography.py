from __future__ import annotations

import pytest

from src.services.bank_geography import (
    BankCountry,
    family_of,
    load_country_geo,
    load_lookup,
    resolve,
    resolve_all,
)


@pytest.fixture(scope="module")
def lookup() -> dict[str, BankCountry]:
    return load_lookup()


def test_serial_number_is_stripped_so_every_branch_shares_one_entry():
    assert family_of("China Bank #2820") == "China Bank"
    assert family_of("Acme Bancorp") == "Acme Bancorp"


def test_country_written_in_the_name_is_read_not_inferred(lookup):
    decided = resolve("China Bank #2820", lookup)
    assert decided.country_code == "CN"
    assert decided.country_source == "parsed"


def test_us_place_and_us_institution_names_are_assigned(lookup):
    for name in ("First Bank of Danbury", "Savings Bank of Madison", "Arbor Credit Union", "Willows Thrift"):
        decided = resolve(name, lookup)
        assert decided.country_code == "US", name
        assert decided.country_source == "assigned", name


def test_a_name_with_no_signal_stays_unknown_rather_than_guessing(lookup):
    decided = resolve("Zzz Interplanetary Holdings", lookup)
    assert decided.country_code is None
    assert decided.country_source == "unknown"


def test_the_crypto_venue_uses_the_non_country_vasp_anchor(lookup):
    # 99,95% giao dịch của ngân hàng này dùng Bitcoin. Không có pháp vực nào
    # được nêu trong dữ liệu, và đó là điều đáng hiển thị chứ không phải lấp.
    decided = resolve("Crytpo Bank #7", lookup)
    assert decided.is_vasp is True
    assert decided.country_code == "ZZ"
    assert decided.country_source == "assigned"


def test_brand_family_rescues_the_bare_bank_suffix(lookup):
    # "Acme Bank" tự nó không mang dấu hiệu nào, nhưng cùng bộ dữ liệu có
    # "Acme Bancorp" và "Acme Thrift" — loại hình tổ chức tín dụng của Mỹ.
    alone = resolve("Acme Bank", lookup)
    assert alone.country_source == "unknown"

    together = resolve_all(["Acme Bank", "Acme Bancorp", "Acme Thrift"], lookup)
    assert together["Acme Bank"].country_code == "US"
    assert together["Acme Bank"].country_source == "assigned"


def test_brand_family_does_not_reach_a_brand_it_never_saw(lookup):
    together = resolve_all(["Hanoi Bank", "Acme Bancorp"], lookup)
    assert together["Hanoi Bank"].country_source == "unknown"


def test_explicit_lookup_beats_the_us_heuristic(lookup):
    # `UK Bank` khớp bảng tra cứu; không được để luật suy diễn Mỹ ghi đè một
    # dòng sửa tay trong file tham chiếu.
    assert resolve("UK Bank #12", lookup).country_code == "GB"


def test_every_mapped_country_has_coordinates_for_the_map(lookup):
    geo = {row["country_code"] for row in load_country_geo()}
    mapped = {entry.country_code for entry in lookup.values() if entry.country_code}
    assert mapped - geo == set()
    # Quy tắc suy diễn chỉ sinh ra US, nên US phải có toạ độ dù không nằm trong
    # bảng tra cứu tên ngân hàng.
    assert "US" in geo


def test_reference_rows_keep_country_and_source_consistent(lookup):
    for family, entry in lookup.items():
        assert (entry.country_source == "unknown") == (entry.country_code is None), family
