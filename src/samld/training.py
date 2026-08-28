"""Huấn luyện Multi-PNA+EU cho SAML-D — TÁI DÙNG nguyên vòng lặp của mega_pna.

Kiến trúc và vòng huấn luyện (LinkNeighborLoader, ego-id, loss trọng số lớp,
early-stop trên validation F1, chọn ngưỡng trên validation) đều lấy nguyên từ
``src.mega_pna`` — nhánh này chỉ khác ở tầng DỮ LIỆU (đồ thị SAML-D với đặc trưng
quốc gia/tiền tệ/xuyên biên giới). Không tự viết lại GNN.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import torch
import yaml

from src.mega_pna.config import MegaPnaConfig
from src.mega_pna.training import train_one_seed
from src.samld.config import SamldConfig, get_samld_config
from src.samld.data import load_samld
from src.samld.graph_builder import SamldGraphBundle, build_graph
from src.samld.split import temporal_split

logger = logging.getLogger("fin07.samld.training")


def load_yaml_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def build_mega_config(cfg: dict[str, Any], **overrides: Any) -> MegaPnaConfig:
    """Ánh xạ YAML SAML-D → MegaPnaConfig (kiến trúc chung với IBM)."""
    model = cfg.get("model", {})
    train = cfg.get("training", {})
    loss = cfg.get("loss", {})
    params: dict[str, Any] = {
        "hidden_channels": model.get("hidden_channels", 20),
        "num_layers": model.get("num_layers", 2),
        "dropout": model.get("dropout", 0.28),
        "edge_updates": model.get("edge_updates", True),
        "reverse_message_passing": model.get("reverse_message_passing", True),
        "ego_ids": model.get("ego_ids", True),
        "batch_size": train.get("batch_size", 8192),
        "num_neighbors": tuple(train.get("num_neighbors", (100, 100))),
        "learning_rate": train.get("learning_rate", 0.0008),
        "epochs": train.get("epochs", 80),
        "patience": train.get("patience", 0),
        "num_workers": train.get("num_workers", 0),
        "class_weight_clean": loss.get("class_weight_clean", 1.0),
        "class_weight_laundering": loss.get("class_weight_laundering", 7.0),
    }
    params.update(overrides)
    config = MegaPnaConfig(**params)
    config.validate()
    return config


def prepare_bundle(samld_config: SamldConfig | None = None) -> SamldGraphBundle:
    """Nạp SAML-D → split thời gian → đồ thị. Một chỗ để script dùng lại."""
    samld_config = samld_config or get_samld_config()
    df = load_samld(samld_config)
    split = temporal_split(df, samld_config)
    return build_graph(split)


class _SubsampledSplit:
    """Bọc split: giám sát train trên tập con cân bằng lớp, GIỮ nguyên val/test.

    Đồ thị truyền tin vẫn là train đầy đủ; chỉ CẠNH được tính loss bị lấy mẫu
    (giữ toàn bộ dương + ``neg_ratio``× âm). §15 cho phép lấy mẫu train theo lớp;
    val/test giữ phân phối tự nhiên nên chỉ số vẫn trung thực.
    """

    def __init__(self, base: Any, train_positions: torch.Tensor, val_positions: torch.Tensor) -> None:
        self._base = base
        self._train = train_positions
        self._val = val_positions

    def positions(self, name: str) -> torch.Tensor:
        # TEST luôn đầy đủ (chỉ số cuối phải trung thực trên phân phối tự nhiên).
        if name == "train":
            return self._train
        if name == "validation":
            return self._val
        return self._base.positions(name)

    def to_dict(self) -> dict[str, Any]:
        d = dict(self._base.to_dict())
        d["train_supervised_subsample"] = int(self._train.numel())
        d["val_supervised_subsample"] = int(self._val.numel())
        return d


def _subsample_train_positions(labels: torch.Tensor, neg_ratio: int, seed: int) -> torch.Tensor:
    pos = (labels == 1).nonzero(as_tuple=False).flatten()
    neg = (labels == 0).nonzero(as_tuple=False).flatten()
    g = torch.Generator().manual_seed(seed)
    n_neg = min(neg.numel(), neg_ratio * max(1, pos.numel()))
    sel = neg[torch.randperm(neg.numel(), generator=g)[:n_neg]]
    return torch.cat([pos, sel]).sort().values


def train_seed(
    bundle: SamldGraphBundle,
    mega_config: MegaPnaConfig,
    *,
    seed: int,
    out_dir: Path,
    device: str = "auto",
    train_neg_ratio: int = 0,
) -> dict[str, Any]:
    """Huấn luyện MỘT seed, lưu checkpoint + predictions + report seed.

    ``train_neg_ratio`` > 0 bật lấy mẫu cạnh giám sát train theo lớp (giữ toàn bộ
    dương + ratio× âm) để một epoch rẻ hơn nhiều mà không đụng val/test.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if train_neg_ratio > 0:
        from src.samld.graph_builder import FORWARD

        base = bundle.mega_bundle.split
        while isinstance(base, _SubsampledSplit):  # tránh bọc chồng khi nhiều seed
            base = base._base
        # train: nhãn của đồ thị train ([:train_end]) trong dải positions("train").
        train_pos_all = base.positions("train")
        train_labels = bundle.mega_bundle.train[FORWARD].y[train_pos_all]
        tr = train_pos_all[_subsample_train_positions(train_labels, train_neg_ratio, seed)]
        # val: nhãn của đồ thị val trong dải positions("validation").
        val_pos_all = base.positions("validation")
        val_labels = bundle.mega_bundle.validation[FORWARD].y[val_pos_all]
        va = val_pos_all[_subsample_train_positions(val_labels, train_neg_ratio, seed + 1)]
        bundle.mega_bundle.split = _SubsampledSplit(base, tr, va)
        logger.info("seed %d: giám sát train %d / val %d cạnh (cân bằng lớp)", seed, tr.numel(), va.numel())
    report = train_one_seed(
        bundle.mega_bundle,
        config=mega_config,
        seed=seed,
        device_name=device,
        checkpoint_path=out_dir / f"model_seed{seed}.pt",
        predictions_path=out_dir / f"predictions_seed{seed}.parquet",
    )
    (out_dir / f"seed{seed}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    logger.info(
        "seed %d xong: val_f1=%.4f test_f1(val-thr)=%.4f",
        seed,
        report["validation_at_best"]["f1"],
        report["test_validation_threshold"]["f1"],
    )
    return report
