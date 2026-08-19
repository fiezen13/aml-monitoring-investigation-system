#!/usr/bin/env python3
"""CLI huấn luyện nhánh Bitcoin AML (Elliptic++ + Random Forest + tinh gọn đặc trưng).

    python -m scripts.train_bitcoin_aml
    python -m scripts.train_bitcoin_aml --data-dir data/raw/elliptic++

Đặt dữ liệu Elliptic++ vào ``data/raw/elliptic++/`` (hoặc trỏ ``--data-dir``),
gồm ba file: txs_features.csv, txs_classes.csv, txs_edgelist.csv. Tải từ repo
chính thức: https://github.com/git-disl/EllipticPlusPlus

Đây là quy trình NGOẠI TUYẾN — không bao giờ chạy lúc backend khởi động.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bitcoin_aml.config import get_bitcoin_config  # noqa: E402
from src.bitcoin_aml.data import DatasetError  # noqa: E402
from src.bitcoin_aml.training import train_pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args() -> argparse.Namespace:
    config = get_bitcoin_config()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=config.data_dir)
    p.add_argument("--artifact-dir", type=Path, default=config.artifact_dir)
    p.add_argument("--n-estimators", type=int, default=config.n_estimators)
    p.add_argument("--seed", type=int, default=config.random_seed)
    p.add_argument("--train-last-timestep", type=int, default=config.train_last_timestep)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = dataclasses.replace(
        get_bitcoin_config(),
        data_dir=args.data_dir,
        artifact_dir=args.artifact_dir,
        n_estimators=args.n_estimators,
        random_seed=args.seed,
        train_last_timestep=args.train_last_timestep,
    )
    try:
        result = train_pipeline(config)
    except DatasetError as exc:
        print(f"\nLỖI DỮ LIỆU: {exc}", file=sys.stderr)
        return 1

    test = result["metrics"]["test"]
    print("\n=== Bitcoin AML — kết quả trên test (illicit là lớp dương) ===")
    print(
        json.dumps(
            {
                "precision_illicit": round(test["precision_illicit"], 4),
                "recall_illicit": round(test["recall_illicit"], 4),
                "f1_illicit": round(test["f1_illicit"], 4),
                "roc_auc": round(test["roc_auc"], 4) if test["roc_auc"] is not None else None,
                "pr_auc": round(test["pr_auc"], 4) if test["pr_auc"] is not None else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nArtifact: {config.artifact_dir}")
    print("Chốt thành nhánh benchmark: python -m scripts.build_bitcoin_release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
