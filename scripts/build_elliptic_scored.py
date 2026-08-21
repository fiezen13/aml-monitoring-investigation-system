"""Rescore Original Elliptic (KHÔNG retrain) vào bitcoin_scored_tx — tái dùng
API + UI + evidence engine sẵn có. Giải thích bằng TÊN ĐẶC TRƯNG PHỤC HỒI
(DFRWS 2026) + percentile, KHÔNG bịa. Đây là NGUỒN SỰ THẬT DUY NHẤT cho /crypto.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

from src.bitcoin_aml.attribution import illicit_contributions
from src.bitcoin_aml.elliptic_explain import top_reasons
from src.bitcoin_aml.elliptic_registry import recovery_stats, registry_by_model_index
from src.bitcoin_aml.evidence import GraphMaps, build_graph_evidence, evidence_reasons, recommended_steps
from src.db.session import get_session

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/elliptic"
ART = ROOT / "data/models/bitcoin_elliptic"
RELEASE = "REL-BTC-ELLIPTIC-ORIG-V1"
MODELV = "bitcoin-elliptic-rf-v1"


def risk_level(p):
    return "CRITICAL" if p >= 0.9 else "HIGH" if p >= 0.7 else "MEDIUM" if p >= 0.4 else "LOW"


def neighbour_sample(tx, succ, pred, known_illicit, model_hi, limit=10):
    by_dir = {}
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


def main():
    rf = joblib.load(ART / "elliptic_rf.joblib")
    reg = registry_by_model_index()
    feat_cols = json.load(open(ART / "selected_features.json"))
    dist = json.load(open(ART / "feature_distribution.json"))
    metrics = json.load(open(ART / "evaluation_metrics.json"))
    feats = pd.read_csv(DATA / "elliptic_txs_features.csv", header=None)
    feats.columns = ["txId", "timestep"] + [f"feature_{i}" for i in range(1, feats.shape[1] - 1)]
    feats["txId"] = feats["txId"].astype(str)
    classes = pd.read_csv(DATA / "elliptic_txs_classes.csv")
    classes["txId"] = classes["txId"].astype(str)
    lab = {r.txId: r["class"] for _, r in classes.iterrows()}
    edges = pd.read_csv(DATA / "elliptic_txs_edgelist.csv")
    c0, c1 = edges.columns[:2]
    from collections import defaultdict

    succ = defaultdict(list)
    pred = defaultdict(list)
    for a, b in zip(edges[c0].astype(str), edges[c1].astype(str)):
        succ[a].append(b)
        pred[b].append(a)
    succ = dict(succ)
    pred = dict(pred)
    known_illicit = {t for t, c in lab.items() if str(c) == "1"}
    known_licit = {t for t, c in lab.items() if str(c) == "2"}

    test = feats[feats.timestep > 34].copy()
    X = test[feat_cols].to_numpy(np.float32)  # noqa: N806 — quy ước ma trận đặc trưng
    ids = test["txId"].tolist()
    ill = list(rf.classes_).index(1)
    proba = rf.predict_proba(X)[:, ill]
    contribs, _ = illicit_contributions(rf, X, ill)
    model_risk = {ids[i]: float(proba[i]) for i in range(len(ids))}
    model_hi = {t for t, p in model_risk.items() if p >= 0.5}
    maps = GraphMaps.build(succ, pred, known_illicit, known_licit, model_risk)

    records = []
    for i, tx in enumerate(ids):
        p = float(proba[i])
        lvl = risk_level(p)
        c = contribs[i].tolist()
        fv = X[i].tolist()
        tr = top_reasons(fv, c, dist, feat_cols, top_k=5)
        # interpretable = |SHAP| từ đặc trưng ĐÃ PHỤC HỒI / tổng |SHAP|
        tot = sum(abs(x) for x in c) or 1e-12
        interp = sum(abs(c[j]) for j in range(len(c)) if reg[j].semantic_status == "RECOVERED_AND_VALIDATED") / tot
        # drivers: top |SHAP|, tên phục hồi (meaningful) hoặc unresolved
        order = sorted(range(len(c)), key=lambda j: abs(c[j]), reverse=True)[:8]
        drivers = [
            {
                "name": reg[j].display_name,
                "label": reg[j].display_name if reg[j].semantic_status == "RECOVERED_AND_VALIDATED" else None,
                "meaningful": reg[j].semantic_status == "RECOVERED_AND_VALIDATED",
                "value": float(fv[j]),
                "contribution": float(c[j]),
            }
            for j in order
        ]
        ge = build_graph_evidence(tx, maps)
        strength = ge["strength"]
        graph_reasons = evidence_reasons(ge, p, "HIGH" if interp >= 0.5 else "MEDIUM")
        # reasons model (semantic) — ưu tiên hiển thị đặc trưng phục hồi (§9/§25)
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
        gn = neighbour_sample(tx, succ, pred, known_illicit, model_hi)
        cls = str(lab.get(tx, "unknown"))
        true_label = "illicit" if cls == "1" else "licit" if cls == "2" else None
        records.append(
            {
                "tx_id": tx,
                "release_id": RELEASE,
                "timestep": int(test.iloc[i]["timestep"]),
                "illicit_prob": round(p, 6),
                "predicted_label": "illicit" if p >= 0.5 else "licit",
                "true_label": true_label,
                "risk_level": lvl,
                "requires_review": lvl in ("HIGH", "CRITICAL"),
                "headline": f"Random Forest chấm {round(p * 100)}% khả năng bất hợp pháp. Nhận định thống kê để ưu tiên rà soát, không phải kết luận.",
                "reasons": json.dumps(reasons, ensure_ascii=False),
                "caveat": "Bộ Elliptic gốc; ngữ nghĩa đặc trưng PHỤC HỒI theo DFRWS 2026 (151/166). Giá trị đã chuẩn hoá — hiển thị percentile, không phải BTC thô. SHAP giải thích hành vi model, không chứng minh typology AML.",
                "drivers": json.dumps(drivers, ensure_ascii=False),
                "meaningful_push_share": round(interp, 4),
                "interpretable_ratio": round(interp, 4),
                "explanation_quality": eq,
                "graph_in_degree": len(pred.get(tx, [])),
                "graph_out_degree": len(succ.get(tx, [])),
                "graph_flagged_neighbours": ge["model_risk_context"]["direct_high_risk_total"],
                "graph_known_illicit_neighbours": ge["ground_truth_exposure"]["direct_known_illicit_total"],
                "graph_neighbours": json.dumps(gn, ensure_ascii=False),
                "evidence_strength": strength,
                "graph_evidence": json.dumps(ge, ensure_ascii=False),
                "evidence_reasons": json.dumps(ev_reasons, ensure_ascii=False),
                "recommended_steps": json.dumps(recommended_steps(ge), ensure_ascii=False),
            }
        )

    ins = text("""INSERT INTO bitcoin_scored_tx (tx_id,release_id,timestep,illicit_prob,predicted_label,true_label,risk_level,requires_review,headline,reasons,caveat,drivers,meaningful_push_share,interpretable_ratio,explanation_quality,graph_in_degree,graph_out_degree,graph_flagged_neighbours,graph_known_illicit_neighbours,graph_neighbours,evidence_strength,graph_evidence,evidence_reasons,recommended_steps)
      VALUES (:tx_id,:release_id,:timestep,:illicit_prob,:predicted_label,:true_label,:risk_level,:requires_review,:headline,CAST(:reasons AS jsonb),:caveat,CAST(:drivers AS jsonb),:meaningful_push_share,:interpretable_ratio,:explanation_quality,:graph_in_degree,:graph_out_degree,:graph_flagged_neighbours,:graph_known_illicit_neighbours,CAST(:graph_neighbours AS jsonb),:evidence_strength,CAST(:graph_evidence AS jsonb),CAST(:evidence_reasons AS jsonb),CAST(:recommended_steps AS jsonb))""")
    zero = "0" * 64
    rel = text("""INSERT INTO edge_model_release (release_id,model_version,dataset,split,model_sha256,scores_sha256,source_database_sha256,threshold,transaction_rows,positive_rows,triggered_rows,feature_count,benchmark,policy,status,trained_at,activated_at)
      VALUES (:rid,:mv,'Elliptic (original)','test',:msha,:z,:z,0.5,:tr,:pos,:trig,166,CAST(:bench AS jsonb),'{}'::jsonb,'reference',now(),NULL)
      ON CONFLICT (release_id) DO UPDATE SET benchmark=EXCLUDED.benchmark,model_version=EXCLUDED.model_version,dataset=EXCLUDED.dataset,transaction_rows=EXCLUDED.transaction_rows,positive_rows=EXCLUDED.positive_rows,triggered_rows=EXCLUDED.triggered_rows""")
    bench = json.dumps(
        {
            "primary_seed": {
                "f1": metrics["f1_illicit"],
                "precision": metrics["precision_illicit"],
                "recall": metrics["recall_illicit"],
                "pr_auc": metrics["pr_auc"],
                "roc_auc": metrics["roc_auc"],
            },
            # Trường thẻ nhánh: để /fc/model-branches vẽ đúng MỘT thẻ Bitcoin (RF).
            "model_kind": "random_forest_classifier",
            "region_label": "Giao dịch Bitcoin",
            "region_description": "Đo trên tập test theo thời gian của Elliptic gốc (các bước thời gian muộn nhất). Random Forest chấm từng giao dịch; KHÔNG leakage-free (DFRWS 2026).",
            "note": "Tái lập benchmark Elliptic (Weber KDD 2019). KHÔNG leakage-free (DFRWS 2026).",
            "reference": {"dataset": "Weber et al. KDD 2019", "semantics": "Šafář et al. DFRWS 2026"},
        },
        ensure_ascii=False,
    )
    msha = hashlib.sha256((ART / "elliptic_rf.joblib").read_bytes()).hexdigest()
    trig = sum(1 for r in records if r["predicted_label"] == "illicit")
    with get_session() as s:
        # Nhánh Bitcoin phục vụ TRỰC TIẾP qua bảng bitcoin_scored_tx, không qua
        # active-join. Nên release này là 'reference', KHÔNG 'active' — không được
        # cướp slot active của release đang phục vụ hàng đợi chính (IBM MEGA-PNA),
        # nếu không mọi phép nối transaction_model_score WHERE status='active' sẽ trượt.
        s.execute(
            rel,
            {
                "rid": RELEASE,
                "mv": MODELV,
                "msha": msha,
                "z": zero,
                "tr": len(records),
                "pos": sum(1 for r in records if r["true_label"] == "illicit"),
                "trig": trig,
                "bench": bench,
            },
        )
        s.execute(text("TRUNCATE bitcoin_scored_tx"))
        for k in range(0, len(records), 2000):
            s.execute(ins, records[k : k + 2000])
        s.commit()
    print(f"scored={len(records)} flagged={trig} recovered_semantics={recovery_stats()['recovered']}/166")


if __name__ == "__main__":
    raise SystemExit(main())
