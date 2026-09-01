"""Registry Elliptic — kiểm chứng theo NGUỒN AUTHORITATIVE (DFRWS 2026 companion).

Ngữ nghĩa được PHỤC HỒI & kiểm chứng bởi Šafář et al. (repo
nesfit/DeanonymizedEllipticBitcoinDataset): 151/166 recovered, 15 unresolved
(4, 8, 16, 113–118, 149–154). Test chống: (a) sai số lượng, (b) bịa tên cho
đặc trưng UNRESOLVED, (c) lệch mapping ở các Feature mốc.
"""

from __future__ import annotations

from src.bitcoin_aml.elliptic_registry import (
    N_FEATURES,
    UNRESOLVED,
    build_registry,
    recovery_stats,
    registry_by_model_index,
)


def test_166_dac_trung_khong_trung_index():
    reg = build_registry()
    assert len(reg) == N_FEATURES == 166
    assert sorted(f.model_index for f in reg) == list(range(166))
    assert sorted(f.dfrws_feature for f in reg) == list(range(1, 167))


def test_so_luong_phuc_hoi_khop_nguon_authoritative():
    stats = recovery_stats()
    assert stats["recovered"] == 151
    assert stats["unresolved"] == 15
    assert stats["unresolved_indexes"] == [4, 8, 16, 113, 114, 115, 116, 117, 118, 149, 150, 151, 152, 153, 154]


def test_mapping_cac_feature_moc():
    """Đối chiếu tên đúng theo kho companion (Feature 1-based)."""
    m = registry_by_model_index()
    expected = {
        1: "Time Step",
        2: "Transaction Volume",
        3: "Fees",
        5: "Number of inputs",
        6: "Number of outputs",
        7: "Number of unique input addresses",
        15: "Number of unique output addresses",
        6: "Number of outputs",  # noqa: F601 - nhấn mạnh ví dụ trong đề
        166: "Spearman correlation between number of outputs of output txs and indices",
    }
    for dfrws, name in expected.items():
        f = m[dfrws - 1]
        assert f.display_name == name, f"Feature {dfrws} lệch: {f.display_name!r} != {name!r}"
        assert f.semantic_status == "RECOVERED_AND_VALIDATED"


def test_unresolved_giu_an_danh_khong_bia():
    m = registry_by_model_index()
    for dfrws in UNRESOLVED:
        f = m[dfrws - 1]
        assert f.semantic_status == "UNRESOLVED"
        assert f.display_name == f"Unresolved Elliptic feature #{dfrws}"
        assert f.category == "UNRESOLVED"


def test_khong_goi_la_ten_chinh_thuc_elliptic():
    """Provenance đúng: đây là PHỤC HỒI, không phải tên chính thức Elliptic công bố."""
    for f in build_registry():
        assert f.official_elliptic_semantic is False
        assert "DFRWS" in f.source or "Šafář" in f.source


def test_time_step_la_count_con_lai_standardized():
    m = registry_by_model_index()
    assert m[0].value_representation == "count"  # Feature 1 = Time Step
    for f in build_registry():
        if f.dfrws_feature != 1:
            assert f.value_representation == "standardized"  # giá trị đã z-score


def test_categories_chi_gan_khi_mapping_ho_tro():
    import collections

    cats = collections.Counter(f.category for f in build_registry())
    assert cats["UNRESOLVED"] == 15
    assert cats["TIME"] == 1
    assert sum(cats.values()) == 166
