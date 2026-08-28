"""Lõi chấm điểm Bitcoin (Elliptic RF) dùng CHUNG cho cả batch và streaming.

`scripts/build_elliptic_scored.py` chấm cả tập test một lần rồi ghi
`bitcoin_scored_tx`. Đường streaming (`src/bitcoin_aml/stream.py`) cần đúng LOGIC
ấy nhưng chạy theo từng lô Kafka tới. Tách phần chung ra đây để hai đường không
trôi khỏi nhau: cùng model, cùng SHAP, cùng evidence, cùng câu chữ.

KHÔNG train lại, KHÔNG đổi model — chỉ tổ chức lại phần lắp ráp bản ghi. Điểm RF
là `predict_proba` từng dòng nên GIỐNG HỆT batch (không phụ thuộc cửa sổ như
nhánh đồ thị SAML-D).

Ngữ cảnh đồ thị (cạnh + nhãn công khai Elliptic) là DỮ LIỆU THAM CHIẾU cố định,
nạp một lần lúc khởi tạo. Chỉ `model_risk` (điểm model của láng giềng) là lớn dần
theo thời gian ở chế độ streaming — evidence "model_risk_context" vì thế đầy dần
khi có thêm giao dịch; phần ground-truth (láng giềng đã biết bất hợp pháp) luôn
đầy đủ vì nhãn là tham chiếu.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.bitcoin_aml.attribution import illicit_contributions
from src.bitcoin_aml.elliptic_explain import top_reasons
from src.bitcoin_aml.elliptic_registry import registry_by_model_index
from src.bitcoin_aml.evidence import (
    GraphMaps,
    build_graph_evidence,
    evidence_reasons,
    recommended_steps,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/raw/elliptic"
ART = ROOT / "data/models/bitcoin_elliptic"

#: Release mặc định của nhánh Bitcoin. Đường streaming ghi cùng release_id để
#: /crypto không phải phân biệt nguồn batch hay stream — cùng một bảng, cùng nhãn.
DEFAULT_RELEASE = "REL-BTC-ELLIPTIC-ORIG-V1"
MODEL_VERSION = "bitcoin-elliptic-rf-v1"

#: Các cột JSONB của bitcoin_scored_tx — tên trùng key trong bản ghi record.
INSERT_SQL = (
    "INSERT INTO bitcoin_scored_tx "
    "(tx_id,release_id,timestep,illicit_prob,predicted_label,true_label,risk_level,"
    "requires_review,headline,reasons,caveat,drivers,meaningful_push_share,"
    "interpretable_ratio,explanation_quality,graph_in_degree,graph_out_degree,"
    "graph_flagged_neighbours,graph_known_illicit_neighbours,graph_neighbours,"
    "evidence_strength,graph_evidence,evidence_reasons,recommended_steps) "
    "VALUES (:tx_id,:release_id,:timestep,:illicit_prob,:predicted_label,:true_label,"
    ":risk_level,:requires_review,:headline,CAST(:reasons AS jsonb),:caveat,"
    "CAST(:drivers AS jsonb),:meaningful_push_share,:interpretable_ratio,"
    ":explanation_quality,:graph_in_degree,:graph_out_degree,:graph_flagged_neighbours,"
    ":graph_known_illicit_neighbours,CAST(:graph_neighbours AS jsonb),:evidence_strength,"
    "CAST(:graph_evidence AS jsonb),CAST(:evidence_reasons AS jsonb),"
    "CAST(:recommended_steps AS jsonb)) "
    # Upsert: streaming có thể chấm lại cùng tx (offset replay) — ghi đè bản mới.
    "ON CONFLICT (tx_id) DO UPDATE SET "
    "release_id=EXCLUDED.release_id,illicit_prob=EXCLUDED.illicit_prob,"
    "predicted_label=EXCLUDED.predicted_label,risk_level=EXCLUDED.risk_level,"
    "requires_review=EXCLUDED.requires_review,headline=EXCLUDED.headline,"
    "reasons=EXCLUDED.reasons,drivers=EXCLUDED.drivers,"
    "meaningful_push_share=EXCLUDED.meaningful_push_share,"
    "interpretable_ratio=EXCLUDED.interpretable_ratio,"
    "explanation_quality=EXCLUDED.explanation_quality,"
    "graph_in_degree=EXCLUDED.graph_in_degree,graph_out_degree=EXCLUDED.graph_out_degree,"
    "graph_flagged_neighbours=EXCLUDED.graph_flagged_neighbours,"
    "graph_known_illicit_neighbours=EXCLUDED.graph_known_illicit_neighbours,"
    "graph_neighbours=EXCLUDED.graph_neighbours,evidence_strength=EXCLUDED.evidence_strength,"
    "graph_evidence=EXCLUDED.graph_evidence,evidence_reasons=EXCLUDED.evidence_reasons,"
    "recommended_steps=EXCLUDED.recommended_steps,scored_at=now()"
)

#: Feature schema Elliptic: txId, timestep, rồi 165 đặc trưng ẩn danh
#: (file gốc có 167 cột). `selected_features.json` gồm 'timestep' + feature_1..165.
FEATURE_COLUMNS = ["txId", "timestep"] + [f"feature_{i}" for i in range(1, 166)]


def risk_level(p: float) -> str:
    """Ngưỡng phân tầng rủi ro — trùng build_elliptic_scored."""
    return "CRITICAL" if p >= 0.9 else "HIGH" if p >= 0.7 else "MEDIUM" if p >= 0.4 else "LOW"


def _neighbour_sample(
    tx: str,
    succ: dict[str, list[str]],
    pred: dict[str, list[str]],
    known_illicit: set[str],
    model_hi: set[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    by_dir: dict[str, str] = {}
    for n in pred.get(tx, []):
        by_dir[n] = "both" if by_dir.get(n) == "out" else "in"
    for n in succ.get(tx, []):
        by_dir[n] = "both" if by_dir.get(n) == "in" else "out"
    ordered = sorted(by_dir, key=lambda n: (n not in known_illicit, n not in model_hi))
    return [
        {
            "id": n,
            "dir": by_dir[n],
            "flag": (n in model_hi) if (n in model_hi or n in known_illicit) else None,
            "known_illicit": n in known_illicit,
        }
        for n in ordered[:limit]
    ]


@dataclass
class BitcoinScoringContext:
    """Model + ngữ cảnh đồ thị đã nạp sẵn, tái dùng qua nhiều lô."""

    rf: Any
    reg: dict[int, Any]
    feat_cols: list[str]
    dist: dict[str, Any]
    succ: dict[str, list[str]]
    pred: dict[str, list[str]]
    known_illicit: set[str]
    known_licit: set[str]
    release_id: str = DEFAULT_RELEASE
    #: Điểm model tích luỹ (streaming lớn dần). tx_id -> P(illicit).
    model_risk: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, release_id: str = DEFAULT_RELEASE) -> BitcoinScoringContext:
        rf = joblib.load(ART / "elliptic_rf.joblib")
        reg = registry_by_model_index()
        feat_cols = json.load(open(ART / "selected_features.json"))
        dist = json.load(open(ART / "feature_distribution.json"))
        classes = pd.read_csv(DATA / "elliptic_txs_classes.csv")
        classes["txId"] = classes["txId"].astype(str)
        lab = {r.txId: r["class"] for _, r in classes.iterrows()}
        edges = pd.read_csv(DATA / "elliptic_txs_edgelist.csv")
        c0, c1 = edges.columns[:2]
        succ: dict[str, list[str]] = defaultdict(list)
        pred: dict[str, list[str]] = defaultdict(list)
        for a, b in zip(edges[c0].astype(str), edges[c1].astype(str)):
            succ[a].append(b)
            pred[b].append(a)
        return cls(
            rf=rf,
            reg=reg,
            feat_cols=feat_cols,
            dist=dist,
            succ=dict(succ),
            pred=dict(pred),
            known_illicit={t for t, c in lab.items() if str(c) == "1"},
            known_licit={t for t, c in lab.items() if str(c) == "2"},
            release_id=release_id,
        )

    @property
    def label_of(self) -> dict[str, str]:
        out = {t: "illicit" for t in self.known_illicit}
        out.update({t: "licit" for t in self.known_licit})
        return out

    def build_records(self, feats: pd.DataFrame) -> list[dict[str, Any]]:
        """Chấm một lô đặc trưng → danh sách bản ghi bitcoin_scored_tx.

        `feats` cần cột txId, timestep và toàn bộ đặc trưng (feature_1..166).
        Cập nhật `self.model_risk` để evidence các lô sau thấy được láng giềng.
        """
        if feats.empty:
            return []
        feats = feats.copy()
        feats["txId"] = feats["txId"].astype(str)
        X = feats[self.feat_cols].to_numpy(np.float32)  # noqa: N806
        ids = feats["txId"].tolist()
        ill = list(self.rf.classes_).index(1)
        proba = self.rf.predict_proba(X)[:, ill]
        contribs, _ = illicit_contributions(self.rf, X, ill)

        # Cập nhật điểm tích luỹ TRƯỚC khi dựng GraphMaps để lô hiện tại cũng
        # thấy nhau trong ngữ cảnh láng giềng.
        for i, tx in enumerate(ids):
            self.model_risk[tx] = float(proba[i])
        model_hi = {t for t, p in self.model_risk.items() if p >= 0.5}
        maps = GraphMaps.build(self.succ, self.pred, self.known_illicit, self.known_licit, self.model_risk)

        records: list[dict[str, Any]] = []
        for i, tx in enumerate(ids):
            p = float(proba[i])
            lvl = risk_level(p)
            c = contribs[i].tolist()
            fv = X[i].tolist()
            tr = top_reasons(fv, c, self.dist, self.feat_cols, top_k=5)
            tot = sum(abs(x) for x in c) or 1e-12
            interp = (
                sum(abs(c[j]) for j in range(len(c)) if self.reg[j].semantic_status == "RECOVERED_AND_VALIDATED") / tot
            )
            order = sorted(range(len(c)), key=lambda j: abs(c[j]), reverse=True)[:8]
            drivers = [
                {
                    "name": self.reg[j].display_name,
                    "label": self.reg[j].display_name
                    if self.reg[j].semantic_status == "RECOVERED_AND_VALIDATED"
                    else None,
                    "meaningful": self.reg[j].semantic_status == "RECOVERED_AND_VALIDATED",
                    "value": float(fv[j]),
                    "contribution": float(c[j]),
                }
                for j in order
            ]
            ge = build_graph_evidence(tx, maps)
            strength = ge["strength"]
            graph_reasons = evidence_reasons(ge, p, "HIGH" if interp >= 0.5 else "MEDIUM")
            model_reasons = [
                {
                    "priority": 3,
                    "badges": ["MODEL"],
                    "title": r["display_name"],
                    "text": f"{'Tăng' if r['direction'] == 'INCREASE_RISK' else 'Giảm'} dự đoán illicit · SHAP {r['shap_value']:+.3f}"
                    + (
                        f" · percentile {round(r['training_percentile'] * 100)} của tập train"
                        if r["training_percentile"] is not None
                        else ""
                    )
                    + (f" · [{r['semantic_status']}]" if r["semantic_status"] != "RECOVERED_AND_VALIDATED" else ""),
                }
                for r in tr
                if r["shap_value"] > 0
            ][:3]
            ev_reasons = sorted(graph_reasons + model_reasons, key=lambda x: x["priority"])[:5]
            top_names = ", ".join(r["display_name"] for r in tr if r["shap_value"] > 0)[:200]
            reasons = [f"Đặc trưng đẩy dự đoán illicit mạnh nhất: {top_names}."] if top_names else []
            eq = "HIGH" if interp >= 0.5 else "MEDIUM" if interp >= 0.35 else "LIMITED"
            gn = _neighbour_sample(tx, self.succ, self.pred, self.known_illicit, model_hi)
            true_label = "illicit" if tx in self.known_illicit else "licit" if tx in self.known_licit else None
            records.append(
                {
                    "tx_id": tx,
                    "release_id": self.release_id,
                    "timestep": int(feats.iloc[i]["timestep"]),
                    "illicit_prob": round(p, 6),
                    "predicted_label": "illicit" if p >= 0.5 else "licit",
                    "true_label": true_label,
                    "risk_level": lvl,
                    "requires_review": lvl in ("HIGH", "CRITICAL"),
                    "headline": f"Random Forest chấm {round(p * 100)}% khả năng bất hợp pháp. "
                    "Nhận định thống kê để ưu tiên rà soát, không phải kết luận.",
                    "reasons": json.dumps(reasons, ensure_ascii=False),
                    "caveat": "Bộ Elliptic gốc; ngữ nghĩa đặc trưng PHỤC HỒI theo DFRWS 2026 (151/166). "
                    "Giá trị đã chuẩn hoá — hiển thị percentile, không phải BTC thô. "
                    "SHAP giải thích hành vi model, không chứng minh typology AML.",
                    "drivers": json.dumps(drivers, ensure_ascii=False),
                    "meaningful_push_share": round(interp, 4),
                    "interpretable_ratio": round(interp, 4),
                    "explanation_quality": eq,
                    "graph_in_degree": len(self.pred.get(tx, [])),
                    "graph_out_degree": len(self.succ.get(tx, [])),
                    "graph_flagged_neighbours": ge["model_risk_context"]["direct_high_risk_total"],
                    "graph_known_illicit_neighbours": ge["ground_truth_exposure"]["direct_known_illicit_total"],
                    "graph_neighbours": json.dumps(gn, ensure_ascii=False),
                    "evidence_strength": strength,
                    "graph_evidence": json.dumps(ge, ensure_ascii=False),
                    "evidence_reasons": json.dumps(ev_reasons, ensure_ascii=False),
                    "recommended_steps": json.dumps(recommended_steps(ge), ensure_ascii=False),
                }
            )
        return records
