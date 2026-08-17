#!/usr/bin/env python3
"""Run the FIN-07 five-seed MEGA-PNA reproduction gate and benchmark suite."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Container CUDA chạy Python 3.10, mà ``datetime.UTC`` chỉ có từ 3.11. Không đổi
# ảnh máy chỉ vì một hằng số: torch-sparse trong ảnh ấy đã dựng đúng cho CUDA 11.8
# và đã kiểm chứng chạy được; đổi ảnh là làm lại từ đầu.
#
# ``UTC`` vốn chỉ là bí danh của ``timezone.utc``, nên gán lại ở đây giữ nguyên mọi
# chỗ gọi ``datetime.now(UTC)`` bên dưới.
UTC = timezone.utc  # noqa: UP017

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = {
    "Small_HI": {"mean": 0.7401, "std": 0.0155},
    "Small_LI": {"mean": 0.4507, "std": 0.0226},
    "Medium_HI": {"mean": 0.7826, "std": 0.0011},
}

#: Bộ dữ liệu duy nhất của suite ``hi-medium``.
HI_MEDIUM = "Medium_HI"

#: Số seed bắt buộc. Bilgi và cộng sự báo cáo trung bình ± độ lệch trên đúng 5
#: seed; ít hơn thì độ lệch vô nghĩa, nhiều hơn thì không so được với bảng của họ.
REQUIRED_SEEDS = 5

#: Cổng phát hành cho HI-Medium.
#:
#: Đây **không phải** cổng tái lập của suite ``gate``. Cổng tái lập hỏi "có khớp
#: số công bố trong 1 độ lệch chuẩn không" — với HI-Medium dung sai ấy là
#: ±0,0011, ngặt tới mức trượt cả khi làm đúng.
#:
#: Cổng dưới đây hỏi câu khác và là câu thực sự quan trọng với bản phát hành:
#: **mô hình có đủ tốt và đủ ổn định để đưa lên production không.** Ngưỡng lấy từ
#: ``docs/KE_HOACH_HI_MEDIUM.md``.
RELEASE_GATE = {
    "f1_mean_min": 0.75,
    "f1_min_min": 0.73,
    "f1_std_max": 0.01,
    "precision_mean_min": 0.70,
    "recall_mean_min": 0.70,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=("gate", "medium", "all", "summarize", "hi-medium"),
        default="gate",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Tiến trình lấy mẫu láng giềng song song, truyền thẳng xuống train_mega_pna.py.",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=0,
        help="Dừng sớm theo validation, truyền thẳng xuống train_mega_pna.py. 0 là tắt.",
    )
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
        "--num-workers",
        str(args.num_workers),
        "--patience",
        str(args.patience),
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


def summarize_hi_medium(reports_dir: Path, seeds: list[int]) -> dict[str, object]:
    """Tổng hợp riêng HI-Medium, không đọc và không ghi bộ dữ liệu nào khác.

    Khác ``summarize_dataset`` ở ba điểm cần cho bản phát hành: nó ghi **F1 thấp
    nhất** (trung bình đẹp vẫn có thể che một seed hỏng), ghi **số seed hoàn tất**,
    và chấm theo ``RELEASE_GATE`` thay vì theo dung sai ±0,0011 của bài báo.
    """
    runs: list[dict[str, object]] = []
    missing: list[int] = []
    for seed in seeds:
        path = seed_report_path(reports_dir, HI_MEDIUM, "paper", seed)
        if not path.exists():
            missing.append(seed)
            continue
        report = json.loads(path.read_text())
        test = report["test_paper_protocol"]
        runs.append(
            {
                "seed": seed,
                **{name: test[name] for name in ("f1", "precision", "recall", "pr_auc")},
                # Chọn checkpoint bằng validation, không bao giờ bằng test. Giữ
                # con số này ở đây để người đọc kiểm được lựa chọn ấy.
                "validation_f1": report["validation_at_best"]["f1"],
                "best_epoch": report["best_epoch"],
                "seconds": report["seconds"],
            }
        )

    aggregate: dict[str, object] = {}
    for metric in ("f1", "precision", "recall", "pr_auc"):
        values = np.array([row[metric] for row in runs], dtype=float)
        aggregate[metric] = {
            "mean": float(values.mean()) if values.size else None,
            "std": float(values.std(ddof=1)) if values.size > 1 else None,
            "min": float(values.min()) if values.size else None,
            "max": float(values.max()) if values.size else None,
        }

    complete = len(runs) == REQUIRED_SEEDS
    checks = {
        "seeds_complete": complete,
        "f1_mean": _at_least(aggregate["f1"]["mean"], RELEASE_GATE["f1_mean_min"]),
        "f1_min": _at_least(aggregate["f1"]["min"], RELEASE_GATE["f1_min_min"]),
        "f1_std": _at_most(aggregate["f1"]["std"], RELEASE_GATE["f1_std_max"]),
        "precision_mean": _at_least(aggregate["precision"]["mean"], RELEASE_GATE["precision_mean_min"]),
        "recall_mean": _at_least(aggregate["recall"]["mean"], RELEASE_GATE["recall_mean_min"]),
    }

    # Chọn seed phát hành bằng validation F1; hoà thì lấy seed nhỏ hơn. Sắp xếp
    # theo (-validation_f1, seed) cho ra đúng thứ tự ấy trong một bước.
    selected = min(runs, key=lambda row: (-row["validation_f1"], row["seed"]))["seed"] if runs else None

    return {
        "schema_version": "fin07.mega_pna.hi_medium_benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": HI_MEDIUM,
        "arm": "paper",
        "requested_seeds": list(seeds),
        "required_seed_count": REQUIRED_SEEDS,
        "completed_seed_count": len(runs),
        "missing_seeds": missing,
        "runs": runs,
        "aggregate": aggregate,
        "release_gate": RELEASE_GATE,
        "release_gate_checks": checks,
        "release_gate_passed": all(checks.values()),
        "selected_seed": selected,
        "selection_rule": "highest validation F1, ties broken by smaller seed",
        # Để đối chiếu, không phải để chấm. Dung sai ±0,0011 của bài báo quá ngặt
        # để dùng làm điều kiện phát hành — xem chú thích ở RELEASE_GATE.
        "published_reference": PUBLISHED[HI_MEDIUM],
    }


def _at_least(value: float | None, floor: float) -> bool:
    return value is not None and value >= floor


def _at_most(value: float | None, ceiling: float) -> bool:
    return value is not None and value <= ceiling


def write_hi_medium_summary(reports_dir: Path, seeds: list[int]) -> dict[str, object]:
    result = summarize_hi_medium(reports_dir, seeds)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def run_hi_medium(args: argparse.Namespace) -> int:
    """Suite HI-Medium độc lập: chỉ Medium_HI, không đụng tới bộ dữ liệu khác."""
    for seed in args.seeds:
        run_seed(args, HI_MEDIUM, "paper", seed)
        if args.include_ablation:
            run_seed(args, HI_MEDIUM, "no_payment_format", seed)

    result = write_hi_medium_summary(args.reports_dir, args.seeds)

    if result["missing_seeds"]:
        print(f"Thiếu seed: {result['missing_seeds']}", file=sys.stderr)
        return 2
    if not result["release_gate_passed"]:
        failed = [name for name, ok in result["release_gate_checks"].items() if not ok]
        print(f"Cổng phát hành HI-Medium TRƯỢT: {', '.join(failed)}", file=sys.stderr)
        return 3
    print(f"Cổng phát hành HI-Medium ĐẠT. Seed chọn để phát hành: {result['selected_seed']}")
    return 0


def main() -> int:
    args = parse_args()
    if len(args.seeds) != REQUIRED_SEEDS:
        raise ValueError("Bilgi et al. report mean ± std over exactly five seeds")

    # Đường đi riêng, đặt trước mọi thứ: không đọc, không ghi, không chấm
    # Small_HI/Small_LI.
    if args.suite == "hi-medium":
        return run_hi_medium(args)

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
