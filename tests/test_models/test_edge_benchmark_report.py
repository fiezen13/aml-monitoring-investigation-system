from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_scientific_edge_benchmark_report_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/render_edge_benchmark_report.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
