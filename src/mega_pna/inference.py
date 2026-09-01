from __future__ import annotations

from pathlib import Path

import pandas as pd
import torch

from .config import MegaPnaConfig
from .data import MegaPnaDataBundle
from .model import MegaPna
from .training import evaluate, make_loaders, resolve_device, set_seed


def score_checkpoint(
    bundle: MegaPnaDataBundle,
    checkpoint_path: Path,
    *,
    device_name: str = "auto",
    output_path: Path | None = None,
    split: str = "test",
) -> dict[str, object]:
    """Chấm điểm một tập bằng checkpoint đã huấn luyện.

    ``split`` mặc định là ``test`` để giữ nguyên hành vi cũ.

    Vì sao cần ``validation``: trọng số hợp nhất phải khớp trên validation. Khớp
    trên test rồi báo cáo cũng trên test là rò rỉ — con số đẹp mà vô giá trị.
    Vòng huấn luyện chỉ ghi điểm của tập test, nên muốn khớp trọng số đúng cách
    thì phải chấm lại validation bằng chính checkpoint này. Đây là **suy luận**,
    không phải huấn luyện lại: rẻ hơn hàng trăm lần.
    """
    if split not in ("train", "validation", "test"):
        raise ValueError(f"split phải thuộc (train, validation, test), nhận {split!r}")

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("schema_version") != "fin07.mega_pna.checkpoint.v1":
        raise ValueError("Unsupported MEGA-PNA checkpoint schema")
    if tuple(checkpoint["feature_names"]) != bundle.feature_names:
        raise ValueError("Checkpoint feature arm does not match formatted data bundle")
    if checkpoint["split"] != bundle.split.to_dict():
        raise ValueError("Checkpoint temporal split does not match the supplied dataset")
    config = MegaPnaConfig(**checkpoint["config"])
    set_seed(int(checkpoint["seed"]))
    device = resolve_device(device_name)
    model = MegaPna(
        node_features=2 if config.ego_ids else 1,
        edge_features=len(bundle.feature_names),
        hidden_channels=config.hidden_channels,
        num_layers=config.num_layers,
        dropout=config.dropout,
        node_degree_hist=checkpoint["node_degree_hist"],
        edge_degree_hist=checkpoint["edge_degree_hist"],
        edge_updates=config.edge_updates,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    loader = make_loaders(bundle, config)[split]
    output = evaluate(
        model,
        loader,
        bundle.split.positions(split),
        device,
        ego_ids=config.ego_ids,
    )
    result = {
        "checkpoint": str(checkpoint_path),
        "split": split,
        "seed": int(checkpoint["seed"]),
        "epoch": int(checkpoint["epoch"]),
        "metrics": output.metrics,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "edge_position": output.edge_ids,
                "source_edge_id": bundle.source_edge_ids[output.edge_ids].numpy(),
                "is_laundering": output.labels,
                "score": output.scores,
            }
        ).to_parquet(output_path, index=False)
        result["predictions_path"] = str(output_path)
    return result
