#!/usr/bin/env python3
"""Load a trained MEGA-PNA checkpoint and reproduce held-out test scores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mega_pna.data import DATASETS, load_formatted_data  # noqa: E402
from src.mega_pna.inference import score_checkpoint  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formatted-dir", type=Path, default=ROOT / "data/processed/mega-pna")
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--split",
        choices=("train", "validation", "test"),
        default="test",
        help="Tập cần chấm. Dùng 'validation' để khớp trọng số hợp nhất mà không chạm test.",
    )
    parser.add_argument("--no-payment-format", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = load_formatted_data(
        args.formatted_dir / args.dataset / "formatted_transactions.csv",
        include_payment_format=not args.no_payment_format,
    )
    result = score_checkpoint(
        bundle,
        args.checkpoint,
        device_name=args.device,
        split=args.split,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
