"""Test CHỐNG RÒ RỈ NHÃN — hàng rào quan trọng nhất của nhánh SAML-D.

Bảo đảm Is_laundering / Laundering_type không bao giờ lọt vào đặc trưng đầu vào.
"""

from __future__ import annotations

import pytest

from src.samld.schema import (
    BINARY_EDGE_FEATURES,
    CATEGORICAL_EDGE_FEATURES,
    EDGE_FEATURE_SOURCE_COLUMNS,
    NUMERIC_EDGE_FEATURES,
    assert_no_label_leakage,
)


def test_no_label_in_edge_features() -> None:
    for name in EDGE_FEATURE_SOURCE_COLUMNS:
        assert name not in ("Is_laundering", "Laundering_type", "label", "typology")


def test_feature_sets_disjoint_from_labels() -> None:
    all_features = set(NUMERIC_EDGE_FEATURES) | set(BINARY_EDGE_FEATURES) | set(CATEGORICAL_EDGE_FEATURES)
    assert not (all_features & {"label", "typology", "Is_laundering", "Laundering_type"})


def test_assert_no_label_leakage_raises() -> None:
    with pytest.raises(ValueError, match="RÒ RỈ NHÃN"):
        assert_no_label_leakage(["amount_log", "label"])
    with pytest.raises(ValueError, match="RÒ RỈ NHÃN"):
        assert_no_label_leakage(["Laundering_type"])


def test_assert_no_label_leakage_passes_clean() -> None:
    assert_no_label_leakage(list(EDGE_FEATURE_SOURCE_COLUMNS))  # không ném lỗi
