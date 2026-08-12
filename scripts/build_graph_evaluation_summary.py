#!/usr/bin/env python3
"""Combine frozen per-detector reports without mixing incompatible protocols."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))


def main() -> int:
    fan = load("fan_final_test_comparison_v1.json")
    gather = load("graph_eval_v2.json")
    cycle = load("graph_eval_cycle_full_v2.json")
    report = {
        "report_version": "graph_evaluation_summary_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol_note": "Metrics remain per-detector; no precision/recall is pooled across detector versions or matching rules.",
        "detectors": {
            "FAN": {"status": "EVALUATED", "source": "fan_final_test_comparison_v1.json", "report": fan},
            "GATHER_SCATTER": {"status": "EVALUATED", "source": "graph_eval_v2.json", "report": gather.get("primary", gather)},
            "CYCLE": {"status": cycle["cycle_evaluation"]["primary"]["status"], "source": "graph_eval_cycle_full_v2.json", "report": cycle["cycle_evaluation"]},
        },
    }
    out = ROOT / "reports/graph_evaluation_summary_v1.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"OK: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
