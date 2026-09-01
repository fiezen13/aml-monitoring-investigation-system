"""Graph detector eval vs IBM GT — FAN, GATHER_SCATTER and CYCLE.

FAN/GATHER match: same detected_pattern, same center account_key,
IBM [t_min, t_max] overlaps detection 7d window. CYCLE uses exact directed
canonical account-cycle signature plus the same window-overlap rule.
Primary metrics: Precision / Recall / F1 on test.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.graph_gt_enrich import (
    GRAPH_TO_IBM,
    IBM_TO_GRAPH,
    enrich_cycle_gt_for_graph_eval,
    enrich_ibm_gt_for_graph_eval,
)
from src.data.snapshot_split import load_split_cutoffs, parse_utc, snapshot_window_bounds

EVAL_PATTERNS = tuple(IBM_TO_GRAPH.values())


def _as_date(value: Any) -> date:
    if hasattr(value, "date") and callable(value.date) and not isinstance(value, type):
        try:
            return value.date()
        except Exception:
            pass
    return pd.Timestamp(value).date()


def window_overlaps_gt(
    *,
    snapshot_date: Any,
    t_min: pd.Timestamp,
    t_max: pd.Timestamp,
) -> bool:
    start, end = snapshot_window_bounds(_as_date(snapshot_date))
    return t_min < end and t_max >= start


def match_detections_to_gt(
    detections: pd.DataFrame,
    gt_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return match edges {instance_id, pattern_instance_id, detected_pattern, sample_split}."""
    if detections.empty or not gt_rows:
        return []
    det = detections.loc[detections["detected_pattern"].isin(EVAL_PATTERNS)].copy()
    if det.empty:
        return []
    # one row per pattern_instance_id (FAN/GATHER: 1:1 with center detection)
    det = det.drop_duplicates(subset=["pattern_instance_id"], keep="first")

    matches: list[dict[str, Any]] = []
    for g in gt_rows:
        t_min = parse_utc(g["t_min"])
        t_max = parse_utc(g["t_max"])
        cand = det.loc[
            (det["detected_pattern"] == g["detected_pattern"]) & (det["account_key"] == g["center_account_key"])
        ]
        for rec in cand.to_dict(orient="records"):
            if window_overlaps_gt(snapshot_date=rec["snapshot_date"], t_min=t_min, t_max=t_max):
                matches.append(
                    {
                        "instance_id": g["instance_id"],
                        "pattern_instance_id": rec["pattern_instance_id"],
                        "detected_pattern": g["detected_pattern"],
                        "sample_split": str(rec["sample_split"]),
                    }
                )
    return matches


def _prf(n_tp_pred: int, n_pred: int, n_tp_gt: int, n_gt: int) -> dict[str, float | int | None]:
    precision = (n_tp_pred / n_pred) if n_pred else None
    recall = (n_tp_gt / n_gt) if n_gt else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {
        "n_gt": n_gt,
        "n_pred": n_pred,
        "n_gt_hit": n_tp_gt,
        "n_pred_hit": n_tp_pred,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compute_split_metrics(
    detections: pd.DataFrame,
    gt_rows: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    *,
    split: str,
) -> dict[str, Any]:
    """Precision/Recall/F1 for one sample_split (primary: test)."""
    det = detections.loc[(detections["sample_split"] == split) & (detections["detected_pattern"].isin(EVAL_PATTERNS))]
    pred_ids = set(det["pattern_instance_id"].unique())
    gt_split = [g for g in gt_rows if g.get("sample_split") == split]
    gt_ids = {g["instance_id"] for g in gt_split}

    m_split = [m for m in matches if m["sample_split"] == split]
    # Restrict to GT assigned to this split (official recall denom)
    gt_hit = {m["instance_id"] for m in m_split if m["instance_id"] in gt_ids}
    pred_hit = {m["pattern_instance_id"] for m in m_split if m["pattern_instance_id"] in pred_ids}

    by_pattern: dict[str, Any] = {}
    for graph_pat in EVAL_PATTERNS:
        gt_p = {g["instance_id"] for g in gt_split if g["detected_pattern"] == graph_pat}
        pred_p = set(det.loc[det["detected_pattern"] == graph_pat, "pattern_instance_id"].unique())
        m_p = [m for m in m_split if m["detected_pattern"] == graph_pat]
        gt_hit_p = {m["instance_id"] for m in m_p if m["instance_id"] in gt_p}
        pred_hit_p = {m["pattern_instance_id"] for m in m_p if m["pattern_instance_id"] in pred_p}
        by_pattern[graph_pat] = {
            "ibm_pattern_type": GRAPH_TO_IBM[graph_pat],
            **_prf(len(pred_hit_p), len(pred_p), len(gt_hit_p), len(gt_p)),
        }

    return {
        "split": split,
        "overall": _prf(len(pred_hit), len(pred_ids), len(gt_hit), len(gt_ids)),
        "by_pattern": by_pattern,
    }


def match_cycle_detections_to_gt(
    evidence: list[dict[str, Any]],
    gt_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match CYCLE evidence by exact directed accounts + window overlap."""
    matches: list[dict[str, Any]] = []
    for gt in gt_rows:
        t_min = parse_utc(gt["t_min"])
        t_max = parse_utc(gt["t_max"])
        signature = tuple(gt["cycle_signature"])
        for ev in evidence:
            if ev.get("detected_pattern") != "CYCLE":
                continue
            if tuple(ev.get("accounts", ())) != signature:
                continue
            if not window_overlaps_gt(snapshot_date=ev["snapshot_date"], t_min=t_min, t_max=t_max):
                continue
            matches.append(
                {
                    "instance_id": gt["instance_id"],
                    "pattern_instance_id": ev["pattern_instance_id"],
                    "sample_split": str(ev.get("sample_split", "")),
                }
            )
    return matches


def compute_cycle_metrics(
    evidence: list[dict[str, Any]],
    gt_rows: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    *,
    split: str,
) -> dict[str, Any]:
    """Compute CYCLE metrics; return NOT_EVALUATED when test GT is absent."""
    gt_split = [g for g in gt_rows if g.get("sample_split") == split]
    pred_split = [e for e in evidence if e.get("sample_split") == split and e.get("detected_pattern") == "CYCLE"]
    pred_ids = {e["pattern_instance_id"] for e in pred_split}
    gt_ids = {g["instance_id"] for g in gt_split}
    m_split = [m for m in matches if m.get("sample_split") == split]
    gt_hit = {m["instance_id"] for m in m_split if m["instance_id"] in gt_ids}
    pred_hit = {m["pattern_instance_id"] for m in m_split if m["pattern_instance_id"] in pred_ids}
    if not gt_ids:
        return {
            "status": "NOT_EVALUATED",
            "reason": f"no eligible CYCLE GT instances in {split} split",
            "split": split,
            "n_gt": 0,
            "n_pred": len(pred_ids),
            "n_gt_hit": 0,
            "n_pred_hit": 0,
            "precision": None,
            "recall": None,
            "f1": None,
        }
    return {
        "status": "EVALUATED",
        "split": split,
        **_prf(len(pred_hit), len(pred_ids), len(gt_hit), len(gt_ids)),
    }


def run_graph_detector_eval(
    *,
    patterns_path: str | Path,
    detection_path: str | Path,
    split_cutoffs_path: str | Path,
    primary_split: str = "test",
    evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    cutoffs = load_split_cutoffs(split_cutoffs_path)
    gt_rows = enrich_ibm_gt_for_graph_eval(patterns_path, split_cutoffs=cutoffs)
    detections = pd.read_parquet(detection_path)
    matches = match_detections_to_gt(detections, gt_rows)

    primary = compute_split_metrics(detections, gt_rows, matches, split=primary_split)
    all_splits = {s: compute_split_metrics(detections, gt_rows, matches, split=s) for s in ("train", "val", "test")}

    cycle_gt = enrich_cycle_gt_for_graph_eval(patterns_path, split_cutoffs=cutoffs)
    cycle_evidence: list[dict[str, Any]] = []
    if evidence_path is not None:
        evidence_file = Path(evidence_path)
        if evidence_file.exists():
            cycle_evidence = [
                json.loads(line) for line in evidence_file.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
    cycle_matches = match_cycle_detections_to_gt(cycle_evidence, cycle_gt["rows"])
    cycle_primary = compute_cycle_metrics(cycle_evidence, cycle_gt["rows"], cycle_matches, split=primary_split)
    return {
        "eval_version": "graph_eval_v1",
        "primary_split": primary_split,
        "match_rule": (
            "same detected_pattern + center_account_key == detection.account_key "
            "+ IBM [t_min,t_max] overlaps detection 7d window"
        ),
        "scope": {
            "patterns": list(EVAL_PATTERNS),
            "cycle_excluded": True,
            "credit": (
                "recall: GT hit if >=1 matching PI in split; "
                "precision: PI hit if >=1 matching GT (edges restricted to split)"
            ),
            "gt_split_assignment": (
                "sample_split from assign_snapshot_split(as_of) where as_of = date(t_max)+1 day 00:00 UTC"
            ),
        },
        "n_gt_enriched": len(gt_rows),
        "n_match_edges": len(matches),
        "gt_by_split": {s: sum(1 for g in gt_rows if g.get("sample_split") == s) for s in ("train", "val", "test")},
        "primary": primary,
        "by_split": all_splits,
        "cycle_evaluation": {
            **cycle_gt,
            "matching_rule": (
                "exact directed canonical account-cycle signature + IBM timestamp interval "
                "overlaps prediction 7d snapshot window; GT blocks outside CYCLE length/window "
                "are excluded, not counted as misses"
            ),
            "n_match_edges": len(cycle_matches),
            "primary": cycle_primary,
            "by_split": {
                s: compute_cycle_metrics(cycle_evidence, cycle_gt["rows"], cycle_matches, split=s)
                for s in ("train", "val", "test")
            },
        },
        "gt_rows": gt_rows,
        "matches": matches,
    }


def write_eval_report(
    report: dict[str, Any],
    *,
    report_path: str | Path,
    gt_out_path: str | Path | None = None,
) -> None:
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Slim JSON for reports (drop bulky match lists optionally keep summary)
    slim = {k: v for k, v in report.items() if k not in ("gt_rows", "matches")}
    slim["n_match_edges"] = report["n_match_edges"]
    report_path.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n")

    if gt_out_path is not None:
        gt_path = Path(gt_out_path)
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        gt_path.write_text(json.dumps(report["gt_rows"], indent=2, ensure_ascii=False) + "\n")
