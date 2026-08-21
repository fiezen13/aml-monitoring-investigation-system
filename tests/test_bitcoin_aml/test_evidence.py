"""Interpretable Investigation Evidence Layer — unit + integration + chống rò nhãn.

Bằng chứng đồ thị tính SAU suy luận, TÁCH ba lớp (model risk / investigation /
explainability). Test bảo đảm: hướng thượng/hạ nguồn đúng, đếm known vs predicted
tách bạch, hop-distance có trần, topology detector đúng, evidence_strength tất
định — bằng chứng đồ thị luôn TÁCH khỏi đặc trưng model (chống rò nhãn của RF
kiểm riêng ở test_elliptic_migration.py).
"""

from __future__ import annotations

from src.bitcoin_aml.evidence import (
    GraphMaps,
    build_graph_evidence,
    detect_topology,
    recommended_steps,
    status_of,
)


def _maps(succ=None, pred=None, known_illicit=None, known_licit=None, model_risk=None) -> GraphMaps:
    return GraphMaps.build(
        succ=succ or {},
        pred=pred or {},
        known_illicit=set(known_illicit or []),
        known_licit=set(known_licit or []),
        model_risk=model_risk or {},
    )


# Chống rò nhãn của RF Elliptic (đặc trưng đầu vào không chứa nhãn/láng giềng)
# được kiểm ở tests/test_bitcoin_aml/test_elliptic_migration.py — file này chỉ lo
# lớp bằng chứng đồ thị (evidence.py), tính SAU và TÁCH khỏi đặc trưng model.

# --- Hướng + đếm ------------------------------------------------------------


def test_upstream_la_predecessor_downstream_la_successor():
    # I -> T -> D : I thượng nguồn, D hạ nguồn.
    maps = _maps(succ={"T": ["D"]}, pred={"T": ["I"]})
    ev = build_graph_evidence("T", maps)
    assert ev["direct_context"]["upstream_count"] == 1
    assert ev["direct_context"]["downstream_count"] == 1


def test_known_illicit_tach_khoi_model_predicted():
    # U (thượng nguồn) có NHÃN THẬT illicit; D (hạ nguồn) chỉ MODEL dự đoán rủi ro.
    maps = _maps(succ={"T": ["D"]}, pred={"T": ["U"]}, known_illicit=["U"], model_risk={"D": 0.9})
    ev = build_graph_evidence("T", maps)
    gt = ev["ground_truth_exposure"]
    mr = ev["model_risk_context"]
    assert gt["direct_known_illicit_upstream"] == 1 and gt["direct_known_illicit_total"] == 1
    assert mr["direct_high_risk_downstream"] == 1
    assert status_of("U", maps) == "KNOWN_ILLICIT" and status_of("D", maps) == "MODEL_HIGH_RISK"


# --- Hop distance -----------------------------------------------------------


def test_nearest_known_illicit_hop_2():
    # T -> A -> B(illicit): illicit ở 2 hop.
    maps = _maps(succ={"T": ["A"], "A": ["B"]}, pred={"A": ["T"], "B": ["A"]}, known_illicit=["B"])
    ev = build_graph_evidence("T", maps)
    assert ev["ground_truth_exposure"]["nearest_known_illicit_hop"] == 2


def test_nearest_hop_null_khi_ngoai_pham_vi():
    maps = _maps(succ={"T": ["A"]}, pred={"A": ["T"]}, known_illicit=["Z"])  # Z không nối
    ev = build_graph_evidence("T", maps)
    assert ev["ground_truth_exposure"]["nearest_known_illicit_hop"] is None  # không ghi 'infinite'


# --- Topology detectors -----------------------------------------------------


def test_fan_in_detector():
    pats = detect_topology(in_degree=8, out_degree=1, chain_len=1)
    assert any(p["type"] == "FAN_IN" for p in pats)
    assert not any(p["type"] == "FAN_OUT" for p in pats)


def test_fan_out_detector():
    pats = detect_topology(in_degree=1, out_degree=8, chain_len=1)
    assert any(p["type"] == "FAN_OUT" for p in pats)


def test_gather_scatter_detector():
    pats = detect_topology(in_degree=6, out_degree=6, chain_len=1)
    assert any(p["type"] == "GATHER_SCATTER" for p in pats)
    # gather-scatter thay cho fan-in/out, không chồng.
    assert not any(p["type"] in ("FAN_IN", "FAN_OUT") for p in pats)


def test_linear_chain_detector():
    pats = detect_topology(in_degree=1, out_degree=1, chain_len=5)
    assert any(p["type"] == "LINEAR_CHAIN" for p in pats)


def test_chain_length_tinh_qua_build():
    # T -> A -> B -> C -> D, mỗi trung gian in=out=1 → chuỗi dài 5.
    succ = {"T": ["A"], "A": ["B"], "B": ["C"], "C": ["D"]}
    pred = {"A": ["T"], "B": ["A"], "C": ["B"], "D": ["C"]}
    ev = build_graph_evidence("T", _maps(succ=succ, pred=pred))
    assert ev["topology"]["max_linear_chain"] >= 4


# --- Evidence strength (tất định, tách khỏi model risk) ---------------------


def test_strength_strong_khi_co_direct_known_illicit():
    maps = _maps(pred={"T": ["U"]}, known_illicit=["U"])
    ev = build_graph_evidence("T", maps)
    assert ev["strength"] == "STRONG"


def test_strength_none_khi_lan_can_sach():
    maps = _maps(succ={"T": ["A"]}, pred={"A": ["T"]})  # A unknown
    ev = build_graph_evidence("T", maps)
    assert ev["strength"] == "NONE"


def test_case_c_model_risk_thap_van_giu_evidence_doc_lap():
    """CASE C: điểm model thấp NHƯNG có known-illicit — hai lớp không gộp.

    evidence_strength phản ánh bằng chứng đồ thị, KHÔNG bị model risk kéo.
    """
    maps = _maps(pred={"T": ["U"]}, known_illicit=["U"])
    ev = build_graph_evidence("T", maps)
    assert ev["strength"] == "STRONG"  # dù model risk có thể thấp, bằng chứng vẫn mạnh


# --- Biên: null graph + trần số nút -----------------------------------------


def test_null_graph_context_khong_vo():
    ev = build_graph_evidence("ISOLATED", _maps())
    assert ev["direct_context"]["total"] == 0
    assert ev["strength"] == "NONE"
    assert recommended_steps(ev)  # vẫn có gợi ý (mở rộng đồ thị)


def test_node_budget_cap_khong_treo_voi_hub():
    # Nút hub: 1000 hạ nguồn → phải cắt theo NODE_BUDGET, không treo.
    succ = {"T": [f"n{i}" for i in range(1000)]}
    ev = build_graph_evidence("T", _maps(succ=succ))
    assert ev["direct_context"]["downstream_count"] == 1000  # bậc thật vẫn đếm đủ
    assert ev["neighborhood"]["one_hop"]["total"] <= 600  # nhưng vùng duyệt bị cắt


def test_recommended_steps_sinh_tu_bang_chung_that():
    maps = _maps(pred={"T": ["U"]}, known_illicit=["U"])
    steps = recommended_steps(build_graph_evidence("T", maps))
    assert any("bất hợp pháp đã biết" in s for s in steps)
