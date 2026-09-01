"""Test lấy mẫu cạnh giám sát theo lớp + dựng đồ thị inference."""

from __future__ import annotations

from pathlib import Path

import torch

from src.samld.config import SamldConfig
from src.samld.data import load_samld
from src.samld.encoders import fit_edge_encoder
from src.samld.graph_builder import FORWARD, build_inference_graph
from src.samld.split import temporal_split
from src.samld.training import _subsample_train_positions


def test_subsample_keeps_all_positives() -> None:
    labels = torch.tensor([0, 0, 1, 0, 0, 0, 1, 0, 0, 0])  # 2 dương / 10
    idx = _subsample_train_positions(labels, neg_ratio=2, seed=0)
    kept = labels[idx]
    # giữ TOÀN BỘ dương
    assert int((kept == 1).sum()) == 2
    # âm bị cắt còn ~ratio× dương (2×2=4)
    assert int((kept == 0).sum()) == 4


def test_subsample_ratio_capped_by_available() -> None:
    labels = torch.tensor([1, 1, 0])  # chỉ 1 âm
    idx = _subsample_train_positions(labels, neg_ratio=100, seed=1)
    assert int((labels[idx] == 0).sum()) == 1  # không vượt số âm có thật


def test_build_inference_graph(raw_samld_csv: Path) -> None:
    cfg = SamldConfig(raw_csv=raw_samld_csv)
    df = load_samld(cfg)
    split = temporal_split(df, cfg)
    encoder = fit_edge_encoder(split.train)
    graph, ids = build_inference_graph(split.test, encoder)
    # đồ thị chấm: mọi cạnh có mặt, đặc trưng khớp encoder
    assert graph[FORWARD].edge_index.size(1) == len(split.test)
    assert graph[FORWARD].edge_attr.size(1) == encoder.num_features
    assert len(ids) == len(split.test)
