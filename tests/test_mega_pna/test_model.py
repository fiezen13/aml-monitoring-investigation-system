from __future__ import annotations

import torch
from torch_geometric.data import HeteroData

from src.mega_pna.model import MegaPna, degree_histogram, parallel_edge_histogram


def graph() -> HeteroData:
    data = HeteroData()
    edge_index = torch.tensor([[0, 0, 1, 2, 2], [1, 1, 2, 0, 1]])
    data["node"].x = torch.tensor([[1.0, 1.0], [1.0, 0.0], [1.0, 1.0]])
    data["node", "to", "node"].edge_index = edge_index
    data["node", "to", "node"].edge_attr = torch.randn(5, 4)
    data["node", "rev_to", "node"].edge_index = edge_index.flip(0)
    data["node", "rev_to", "node"].edge_attr = torch.randn(5, 4)
    return data


def test_degree_histograms_collapse_parallel_edges() -> None:
    data = graph()
    edge_index = data["node", "to", "node"].edge_index
    assert parallel_edge_histogram(edge_index).tolist() == [0, 3, 1]
    # Unique in-degrees are [1, 2, 1], so two nodes have degree 1 and one has 2.
    assert degree_histogram(edge_index, 3).tolist() == [0, 2, 1]


def test_mega_pna_produces_one_logit_pair_per_original_edge() -> None:
    data = graph()
    combined = torch.cat(
        (
            data["node", "to", "node"].edge_index,
            data["node", "rev_to", "node"].edge_index,
        ),
        dim=1,
    )
    model = MegaPna(
        node_features=2,
        edge_features=4,
        hidden_channels=20,
        num_layers=2,
        node_degree_hist=degree_histogram(combined, 3),
        edge_degree_hist=parallel_edge_histogram(data["node", "to", "node"].edge_index),
    )
    logits = model(data)
    assert logits.shape == (5, 2)
    logits.sum().backward()
    without_grad = [name for name, parameter in model.named_parameters() if parameter.grad is None]
    # The last reverse edge-update is retained for layer symmetry/checkpoint
    # parity, but no later node layer consumes its output in edge classification.
    assert without_grad == [
        "layers.1.reverse_edge_update.0.weight",
        "layers.1.reverse_edge_update.0.bias",
        "layers.1.reverse_edge_update.2.weight",
        "layers.1.reverse_edge_update.2.bias",
    ]
