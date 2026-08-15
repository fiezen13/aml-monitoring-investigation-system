#!/usr/bin/env python3
"""Run the FIN-07 five-seed MEGA-PNA reproduction gate and benchmark suite."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = {
    "Small_HI": {"mean": 0.7401, "std": 0.0155},
    "Small_LI": {"mean": 0.4507, "std": 0.0226},
    "Medium_HI": {"mean": 0.7826, "std": 0.0011},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("gate", "medium", "all", "summarize"), default="gate")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--include-ablation", action="store_true")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports/mega-pna")
    return parser.parse_args()


def seed_report_path(reports_dir: Path, dataset: str, arm: str, seed: int) -> Path:
    return reports_dir / dataset / arm / f"seed_{seed}.json"


def run_seed(args: argparse.Namespace, dataset: str, arm: str, seed: int) -> None:
    report = seed_report_path(args.reports_dir, dataset, arm, seed)
    if report.exists():
        existing = json.loads(report.read_text())
        config = existing.get("config", {})
        if config.get("epochs") == args.epochs and config.get("batch_size") == args.batch_size:
            print(f"Reuse {report}", flush=True)
            return
        raise RuntimeError(f"{report} was produced with a different epoch/batch config; move it aside before rerun")
    command = [
        sys.executable,
        str(ROOT / "scripts/train_mega_pna.py"),
        "--dataset",
        dataset,
        "--seed",
        str(seed),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--device",
        args.device,
        "--reports-dir",
        str(args.reports_dir),
    ]
    if arm == "no_payment_format":
        command.append("--no-payment-format")
    subprocess.run(command, cwd=ROOT, check=True)


def summarize_dataset(
    reports_dir: Path,
    dataset: str,
    arm: str,
    seeds: list[int],
) -> dict[str, object]:
    rows = []
    for seed in seeds:
        path = seed_report_path(reports_dir, dataset, arm, seed)
        if not path.exists():
            continue
        report = json.loads(path.read_text())
        rows.append(
            {
                "seed": seed,
                **{name: report["test_paper_protocol"][name] for name in ("f1", "precision", "recall", "pr_auc")},
                "best_epoch": report["best_epoch"],
                "seconds": report["seconds"],
            }
        )
    if not rows:
        return {"dataset": dataset, "arm": arm, "complete": False, "runs": []}
    aggregate = {}
    for metric in ("f1", "precision", "recall", "pr_auc"):
        values = np.array([row[metric] for row in rows], dtype=float)
        aggregate[metric] = {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=1)) if len(values) > 1 else None,
        }
    expected = PUBLISHED[dataset]
    gate_pass = None
    if arm == "paper" and len(rows) == 5:
        gate_pass = abs(aggregate["f1"]["mean"] - expected["mean"]) <= expected["std"]
    return {
        "dataset": dataset,
        "arm": arm,
        "complete": len(rows) == len(seeds),
        "runs": rows,
        "aggregate": aggregate,
        "published_reference": expected,
        "within_published_one_std": gate_pass,
    }


def write_summary(args: argparse.Namespace, datasets: list[str]) -> dict[str, object]:
    arms = ["paper", "no_payment_format"] if args.include_ablation else ["paper"]
    summaries = [summarize_dataset(args.reports_dir, dataset, arm, args.seeds) for dataset in datasets for arm in arms]
    by_key = {(row["dataset"], row["arm"]): row for row in summaries}
    small_gate = all(
        by_key.get((dataset, "paper"), {}).get("within_published_one_std") is True
        for dataset in ("Small_HI", "Small_LI")
    )
    result = {
        "schema_version": "fin07.mega_pna.benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "seeds": args.seeds,
        "required_seed_count": 5,
        "small_reproduction_gate_passed": small_gate,
        "datasets": summaries,
    }
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    path = args.reports_dir / "benchmark.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    args = parse_args()
    if len(args.seeds) != 5:
        raise ValueError("Bilgi et al. report mean ± std over exactly five seeds")
    small = ["Small_HI", "Small_LI"]
    if args.suite != "summarize":
        if args.suite in ("gate", "all"):
            for dataset in small:
                for seed in args.seeds:
                    run_seed(args, dataset, "paper", seed)
                    if args.include_ablation:
                        run_seed(args, dataset, "no_payment_format", seed)
            gate = write_summary(args, small)
            if not gate["small_reproduction_gate_passed"]:
                print("Small reproduction gate failed; Medium_HI is blocked.", file=sys.stderr)
                return 2
        if args.suite in ("medium", "all"):
            existing = write_summary(args, small)
            if not existing["small_reproduction_gate_passed"]:
                print("Run and pass --suite gate before Medium_HI.", file=sys.stderr)
                return 2
            for seed in args.seeds:
                run_seed(args, "Medium_HI", "paper", seed)
                if args.include_ablation:
                    run_seed(args, "Medium_HI", "no_payment_format", seed)
    datasets = [*small, "Medium_HI"] if args.suite in ("medium", "all", "summarize") else small
    write_summary(args, datasets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
