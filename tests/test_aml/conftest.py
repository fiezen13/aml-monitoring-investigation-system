"""Đồ dùng chung cho kiểm thử luồng nạp AML."""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "aml"
FIXTURE_CSV = FIXTURE_DIR / "HI-Sample_Trans.csv"


@pytest.fixture(scope="session")
def fixture_csv() -> Path:
    assert FIXTURE_CSV.exists(), f"Thiếu file mẫu {FIXTURE_CSV}. Sinh lại bằng: python scripts/aml/make_fixture.py"
    return FIXTURE_CSV
