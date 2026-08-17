#!/usr/bin/env python3
"""Train one reproducible MEGA-PNA seed on an IBM AML dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mega_pna.config import MegaPnaConfig  # noqa: E402
from src.mega_pna.data import DATASETS, load_formatted_data  # noqa: E402
from src.mega_pna.training import train_one_seed, write_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--formatted-dir", type=Path, default=ROOT / "data/processed/mega-pna")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "models/mega-pna")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports/mega-pna")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Tiến trình lấy mẫu láng giềng song song. 0 giữ hành vi cũ; trên máy 8 nhân nên đặt 6.",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=0,
        help="Dừng khi validation F1 không cải thiện sau ngần này epoch. 0 là tắt.",
    )
    parser.add_argument("--no-payment-format", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    arm = "no_payment_format" if args.no_payment_format else "paper"
    formatted = args.formatted_dir / args.dataset / "formatted_transactions.csv"
    if not formatted.exists():
        raise FileNotFoundError(f"{formatted} does not exist; run scripts/format_mega_pna.py first")
    config = MegaPnaConfig(
        epochs=args.epochs, batch_size=args.batch_size, num_workers=args.num_workers, patience=args.patience
    )
    bundle = load_formatted_data(
        formatted,
        include_payment_format=not args.no_payment_format,
    )
    report = train_one_seed(
        bundle,
        config=config,
        seed=args.seed,
        device_name=args.device,
        checkpoint_path=args.output_dir / args.dataset / arm / f"seed_{args.seed}.pt",
        predictions_path=args.output_dir / args.dataset / arm / f"seed_{args.seed}_test.parquet",
    )
    report.update({"dataset": args.dataset, "arm": arm, "formatted_path": str(formatted)})
    output = args.reports_dir / args.dataset / arm / f"seed_{args.seed}.json"
    write_report(output, report)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
