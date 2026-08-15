from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MegaPnaConfig:
    """Paper-compatible hyperparameters for AML edge classification."""

    hidden_channels: int = 20
    num_layers: int = 2
    batch_size: int = 8192
    num_neighbors: tuple[int, int] = (100, 100)
    learning_rate: float = 0.0008
    dropout: float = 0.28
    class_weight_clean: float = 1.0
    class_weight_laundering: float = 7.0
    epochs: int = 80
    edge_updates: bool = True
    reverse_message_passing: bool = True
    ego_ids: bool = True
    flatten_parallel_edges: bool = True
    edge_aggregation: str = "pna"
    node_aggregation: str = "pna"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if self.hidden_channels % 5:
            raise ValueError("hidden_channels must be divisible by the five PNA towers")
        if self.num_layers != len(self.num_neighbors):
            raise ValueError("num_neighbors must contain one value per GNN layer")
        if not all(self.num_neighbors):
            raise ValueError("neighbor sample sizes must be positive")
        if self.edge_aggregation != "pna" or self.node_aggregation != "pna":
            raise ValueError("This FIN-07 implementation intentionally supports MEGA-PNA only")
