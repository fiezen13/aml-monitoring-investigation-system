#!/usr/bin/env python3
"""Run FIN-07 Task 2: IBM pattern inventory + typology coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.task2_pipeline import run_task2_typology  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-07 Task 2 typology mapping")
    parser.add_argument(
        "--patterns",
        type=Path,
        default=ROOT / "data/raw/ibm-aml/LI-Small_Patterns.txt",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "docs/reference/typology_mapping_catalog_v1.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data/processed",
    )
    args = parser.parse_args()

    if not args.patterns.exists():
        print(f"Pattern file not found: {args.patterns}", file=sys.stderr)
        return 1
    if not args.catalog.exists():
        print(f"Catalog not found: {args.catalog}", file=sys.stderr)
        return 1

    result = run_task2_typology(args.patterns, args.catalog, args.out_dir)
    print(
        f"OK: {result['n_instances']} instances; "
        f"type_coverage={result['covered_typology_count']}/10 "
        f"({result['type_coverage']:.0%})"
    )
    if result.get("checksum_warning"):
        print(f"WARNING: {result['checksum_warning']}")
    for name, path in result["artifacts"].items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
