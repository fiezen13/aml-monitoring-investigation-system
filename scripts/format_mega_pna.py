#!/usr/bin/env python3
"""Format IBM AML CSVs into Bilgi et al.'s ten-column MEGA-GNN contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mega_pna.data import DATASETS, format_kaggle_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], default="all")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/ibm-aml")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/mega-pna")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    names = list(DATASETS) if args.dataset == "all" else [args.dataset]
    manifests = []
    for name in names:
        raw = args.raw_dir / DATASETS[name]
        if not raw.exists():
            raise FileNotFoundError(raw)
        output = args.output_dir / name / "formatted_transactions.csv"
        print(f"Formatting {name}: {raw} -> {output}", flush=True)
        manifests.append(format_kaggle_file(raw, output, force=args.force))
    print(json.dumps(manifests, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
