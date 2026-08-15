from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import Tensor, nn
from torch_geometric.data import HeteroData
from torch_geometric.nn import BatchNorm, PNAConv
from torch_geometric.nn.aggr import DegreeScalerAggregation

PNA_AGGREGATORS = ("mean", "min", "max", "std")
PNA_SCALERS = ("identity", "amplification", "attenuation")


def _safe_histogram(histogram: Tensor | Sequence[int]) -> Tensor:
    value = torch.as_tensor(histogram, dtype=torch.long).flatten().cpu()
    if value.numel() == 0 or int(value.sum()) == 0:
        return torch.ones(1, dtype=torch.long)
    return value


def degree_histogram(edge_index: Tensor, num_nodes: int) -> Tensor:
    """PNA in-degree histogram after parallel edges have been collapsed."""

    pairs = torch.unique(edge_index.t().cpu(), dim=0)
    degree = torch.bincount(pairs[:, 1], minlength=num_nodes)
    return torch.bincount(degree, minlength=1)


def parallel_edge_histogram(edge_index: Tensor) -> Tensor:
    """Histogram of the number of parallel transactions for each directed pair."""

    _, counts = torch.unique(edge_index.t().cpu(), dim=0, return_counts=True)
    return torch.bincount(counts, minlength=1)


class PnaMultiEdgeAggregation(nn.Module):
    """First MEGA stage: aggregate parallel edges before node aggregation."""

    def __init__(self, hidden_channels: int, degree_hist: Tensor | Sequence[int]) -> None:
        super().__init__()
        self.aggregate = DegreeScalerAggregation(
            list(PNA_AGGREGATORS),
            list(PNA_SCALERS),
            _safe_histogram(degree_hist),
        )
        self.project = nn.Linear(
            len(PNA_AGGREGATORS) * len(PNA_SCALERS) * hidden_channels,
            hidden_channels,
        )

    def reset_parameters(self) -> None:
        self.aggregate.reset_parameters()
        self.project.reset_parameters()

    def forward(self, edge_index: Tensor, edge_attr: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        simple_edges, inverse = torch.unique(edge_index.t(), dim=0, return_inverse=True)
        aggregated = self.project(self.aggregate(edge_attr, inverse, dim_size=simple_edges.size(0)))
        return simple_edges.t().contiguous(), aggregated, inverse


class MegaPnaLayer(nn.Module):
    """Bi-directional two-stage MEGA-PNA message-passing layer.

    Forward and reverse relations have independent message functions, matching
    the relation-specific modules produced by the official implementation's
    ``to_hetero`` conversion. Their node messages are combined by a mean.
    """

    def __init__(
        self,
        hidden_channels: int,
        node_degree_hist: Tensor | Sequence[int],
        edge_degree_hist: Tensor | Sequence[int],
        *,
        edge_updates: bool,
    ) -> None:
        super().__init__()
        common = dict(
            in_channels=hidden_channels,
            out_channels=hidden_channels,
            aggregators=list(PNA_AGGREGATORS),
            scalers=list(PNA_SCALERS),
            deg=_safe_histogram(node_degree_hist),
            edge_dim=hidden_channels,
            towers=5,
            pre_layers=1,
            post_layers=1,
            divide_input=False,
        )
        self.forward_edge_aggregation = PnaMultiEdgeAggregation(hidden_channels, edge_degree_hist)
        self.reverse_edge_aggregation = PnaMultiEdgeAggregation(hidden_channels, edge_degree_hist)
        self.forward_conv = PNAConv(**common)
        self.reverse_conv = PNAConv(**common)
        self.batch_norm = BatchNorm(hidden_channels)
        self.edge_updates = edge_updates
        if edge_updates:
            self.forward_edge_update = self._edge_mlp(hidden_channels)
            self.reverse_edge_update = self._edge_mlp(hidden_channels)

    @staticmethod
    def _edge_mlp(hidden_channels: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Linear(3 * hidden_channels, hidden_channels),
            nn.ReLU(),
            nn.Linear(hidden_channels, hidden_channels),
        )

    def forward(
        self,
        x: Tensor,
        forward_edge_index: Tensor,
        forward_edge_attr: Tensor,
        reverse_edge_index: Tensor,
        reverse_edge_attr: Tensor,
    ) -> tuple[Tensor, Tensor, Tensor]:
        f_index, f_aggregated, f_inverse = self.forward_edge_aggregation(forward_edge_index, forward_edge_attr)
        r_index, r_aggregated, r_inverse = self.reverse_edge_aggregation(reverse_edge_index, reverse_edge_attr)

        forward_message = self.forward_conv(x, f_index, f_aggregated)
        reverse_message = self.reverse_conv(x, r_index, r_aggregated)
        relation_mean = (forward_message + reverse_message) / 2
        x = (x + torch.relu(self.batch_norm(relation_mean))) / 2

        if self.edge_updates:
            f_src = forward_edge_index[0]
            r_src = reverse_edge_index[0]
            f_parallel = f_aggregated.index_select(0, f_inverse)
            r_parallel = r_aggregated.index_select(0, r_inverse)
            forward_delta = self.forward_edge_update(torch.cat((x[f_src], f_parallel, forward_edge_attr), dim=-1))
            reverse_delta = self.reverse_edge_update(torch.cat((x[r_src], r_parallel, reverse_edge_attr), dim=-1))
            forward_edge_attr = forward_edge_attr + forward_delta / 2
            reverse_edge_attr = reverse_edge_attr + reverse_delta / 2

        return x, forward_edge_attr, reverse_edge_attr


class MegaPna(nn.Module):
    """MEGA-PNA edge classifier used in Bilgi et al.'s AML experiments."""

    FORWARD = ("node", "to", "node")
    REVERSE = ("node", "rev_to", "node")

    def __init__(
        self,
        *,
        node_features: int,
        edge_features: int,
        hidden_channels: int = 20,
        num_layers: int = 2,
        dropout: float = 0.28,
        node_degree_hist: Tensor | Sequence[int],
        edge_degree_hist: Tensor | Sequence[int],
        edge_updates: bool = True,
    ) -> None:
        super().__init__()
        self.hidden_channels = hidden_channels
        self.register_buffer("node_degree_hist", _safe_histogram(node_degree_hist))
        self.register_buffer("edge_degree_hist", _safe_histogram(edge_degree_hist))
        self.node_embedding = nn.Linear(node_features, hidden_channels)
        self.forward_edge_embedding = nn.Linear(edge_features, hidden_channels)
        self.reverse_edge_embedding = nn.Linear(edge_features, hidden_channels)
        self.layers = nn.ModuleList(
            MegaPnaLayer(
                hidden_channels,
                self.node_degree_hist,
                self.edge_degree_hist,
                edge_updates=edge_updates,
            )
            for _ in range(num_layers)
        )
        self.classifier = nn.Sequential(
            nn.Linear(3 * hidden_channels, 50),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(50, 25),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(25, 2),
        )

    def forward(self, data: HeteroData) -> Tensor:
        x = self.node_embedding(data["node"].x)
        forward_edge_index = data[self.FORWARD].edge_index
        reverse_edge_index = data[self.REVERSE].edge_index
        forward_edge_attr = self.forward_edge_embedding(data[self.FORWARD].edge_attr)
        reverse_edge_attr = self.reverse_edge_embedding(data[self.REVERSE].edge_attr)

        for layer in self.layers:
            x, forward_edge_attr, reverse_edge_attr = layer(
                x,
                forward_edge_index,
                forward_edge_attr,
                reverse_edge_index,
                reverse_edge_attr,
            )

        endpoints = x[forward_edge_index.t()].reshape(-1, 2 * self.hidden_channels).relu()
        return self.classifier(torch.cat((endpoints, forward_edge_attr), dim=-1))
