"""Test graph builder + hợp đồng với model MEGA-PNA (Multi-PNA+EU)."""

from __future__ import annotations

from pathlib import Path

import torch

from src.samld.config import SamldConfig
from src.samld.data import load_samld
from src.samld.graph_builder import FORWARD, build_graph
from src.samld.split import temporal_split


def _bundle(csv: Path):
    cfg = SamldConfig(raw_csv=csv)
    df = load_samld(cfg)
    split = temporal_split(df, cfg)
    return build_graph(split)


def test_graph_shapes_and_no_leak(raw_samld_csv: Path) -> None:
    b = _bundle(raw_samld_csv)
    # cạnh test = toàn bộ (tích luỹ), train < val < test theo số cạnh
    assert b.train[FORWARD].edge_index.size(1) == b.train_end
    assert b.validation[FORWARD].edge_index.size(1) == b.val_end
    assert b.test[FORWARD].edge_index.size(1) >= b.val_end
    # node feature = ones, đúng số node
    assert b.train["node"].x.shape == (b.num_nodes, 1)
    # nhãn KHÔNG nằm trong tên đặc trưng
    assert "label" not in b.feature_names and "typology" not in b.feature_names
    # đặc trưng khớp giữa encoder và graph
    assert b.train[FORWARD].edge_attr.size(1) == b.edge_features == len(b.feature_names)


def test_model_forward_accepts_samld_graph(raw_samld_csv: Path) -> None:
    from src.mega_pna.model import MegaPna, degree_histogram, parallel_edge_histogram

    b = _bundle(raw_samld_csv)
    g = b.train
    idx = g[FORWARD].edge_index
    model = MegaPna(
        node_features=1,
        edge_features=b.edge_features,
        hidden_channels=20,  # phải chia hết cho towers=5 của MEGA-PNA
        num_layers=2,
        node_degree_hist=degree_histogram(idx, b.num_nodes),
        edge_degree_hist=parallel_edge_histogram(idx),
        edge_updates=True,
    )
    model.eval()
    with torch.no_grad():
        logits = model(g)
    # một logit-2-lớp cho mỗi cạnh xuôi
    assert logits.shape == (idx.size(1), 2)
    assert torch.isfinite(logits).all()
