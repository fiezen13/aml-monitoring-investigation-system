from __future__ import annotations

import json
import os
import platform
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch_geometric.data import HeteroData
from torch_geometric.loader import LinkNeighborLoader

from .config import MegaPnaConfig
from .data import MegaPnaDataBundle
from .metrics import best_f1_threshold, binary_metrics, budget_metrics, paper_binary_metrics
from .model import MegaPna, degree_histogram, parallel_edge_histogram

FORWARD = ("node", "to", "node")
REVERSE = ("node", "rev_to", "node")


@dataclass
class EvaluationOutput:
    metrics: dict[str, object]
    edge_ids: np.ndarray
    labels: np.ndarray
    scores: np.ndarray
    logits: np.ndarray


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ["PYTHONHASHSEED"] = str(seed)


def resolve_device(requested: str) -> torch.device:
    if requested != "auto":
        device = torch.device(requested)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS was requested but is not available")
    return device


def preflight_neighbor_sampler() -> None:
    try:
        import torch_sparse  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PyG LinkNeighborLoader needs pyg-lib or torch-sparse. On macOS, install "
            "torch-scatter and torch-sparse with --no-build-isolation after torch."
        ) from exc


def _loader(
    data: HeteroData,
    positions: Tensor,
    config: MegaPnaConfig,
    *,
    shuffle: bool,
) -> LinkNeighborLoader:
    return LinkNeighborLoader(
        data,
        num_neighbors=list(config.num_neighbors),
        edge_label_index=(FORWARD, data[FORWARD].edge_index[:, positions]),
        edge_label=data[FORWARD].y[positions],
        batch_size=config.batch_size,
        shuffle=shuffle,
        num_workers=0,
    )


def make_loaders(bundle: MegaPnaDataBundle, config: MegaPnaConfig) -> dict[str, LinkNeighborLoader]:
    return {
        "train": _loader(
            bundle.train,
            bundle.split.positions("train"),
            config,
            shuffle=True,
        ),
        "validation": _loader(
            bundle.validation,
            bundle.split.positions("validation"),
            config,
            shuffle=False,
        ),
        "test": _loader(
            bundle.test,
            bundle.split.positions("test"),
            config,
            shuffle=False,
        ),
    }


def _add_ego_ids(batch: HeteroData) -> None:
    x = batch["node"].x
    ego = torch.zeros((x.size(0), 1), dtype=x.dtype)
    roots = torch.unique(batch[FORWARD].edge_label_index.reshape(-1))
    ego[roots] = 1
    batch["node"].x = torch.cat((x, ego), dim=1)


def _seed_mask(batch: HeteroData, supervised_positions: Tensor) -> tuple[Tensor, Tensor]:
    input_ids = batch[FORWARD].input_id.detach().cpu()
    seed_ids = supervised_positions[input_ids]
    sampled_ids = batch[FORWARD].edge_id.detach().cpu()
    mask = torch.isin(sampled_ids, seed_ids)
    selected_ids = sampled_ids[mask]
    if selected_ids.numel() != seed_ids.numel() or not torch.equal(
        torch.sort(selected_ids).values, torch.sort(seed_ids).values
    ):
        missing = seed_ids[~torch.isin(seed_ids, selected_ids)]
        raise RuntimeError(f"Neighbor sampler omitted {missing.numel()} supervised edges; refusing a partial metric")
    return mask, selected_ids


def _ensure_seed_edges(
    batch: HeteroData,
    full_data: HeteroData,
    supervised_positions: Tensor,
) -> None:
    """Ensure every supervised edge is present in the sampled message graph.

    LinkNeighborLoader samples neighborhoods around the two endpoint nodes and
    may omit the labelled edge itself. The official AML loop assumes it is
    present and otherwise returns a partial metric. Adding only missing seed
    edges makes the assumption explicit and guarantees one prediction per row.
    """

    input_ids = batch[FORWARD].input_id.detach().cpu()
    seed_ids = supervised_positions[input_ids]
    sorted_node_ids, sorted_to_local = torch.sort(batch["node"].n_id.detach().cpu())
    for relation, reverse in ((FORWARD, False), (REVERSE, True)):
        sampled_ids = batch[relation].edge_id.detach().cpu()
        missing_ids = seed_ids[~torch.isin(seed_ids, sampled_ids)]
        if missing_ids.numel() == 0:
            continue
        global_endpoints = full_data[FORWARD].edge_index[:, missing_ids]
        locations = torch.searchsorted(sorted_node_ids, global_endpoints)
        if not torch.equal(sorted_node_ids[locations], global_endpoints):
            raise RuntimeError("A supervised edge endpoint is absent from its sampled batch")
        local_endpoints = sorted_to_local[locations]
        if reverse:
            local_endpoints = local_endpoints.flip(0)
        store = batch[relation]
        source_store = full_data[relation]
        store.edge_index = torch.cat((store.edge_index, local_endpoints), dim=1)
        store.edge_attr = torch.cat((store.edge_attr, source_store.edge_attr[missing_ids]), dim=0)
        store.edge_id = torch.cat((store.edge_id, missing_ids), dim=0)
        store.timestamps = torch.cat((store.timestamps, source_store.timestamps[missing_ids]), dim=0)
        if relation == FORWARD:
            store.y = torch.cat((store.y, full_data[FORWARD].y[missing_ids]), dim=0)


def _model_from_sample(sample: HeteroData, config: MegaPnaConfig) -> MegaPna:
    combined = torch.cat((sample[FORWARD].edge_index, sample[REVERSE].edge_index), dim=1)
    return MegaPna(
        node_features=sample["node"].x.size(1),
        edge_features=sample[FORWARD].edge_attr.size(1),
        hidden_channels=config.hidden_channels,
        num_layers=config.num_layers,
        dropout=config.dropout,
        node_degree_hist=degree_histogram(combined, sample["node"].num_nodes),
        edge_degree_hist=parallel_edge_histogram(sample[FORWARD].edge_index),
        edge_updates=config.edge_updates,
    )


def _collect(
    model: MegaPna,
    loader: LinkNeighborLoader,
    supervised_positions: Tensor,
    device: torch.device,
    *,
    ego_ids: bool,
    optimizer: torch.optim.Optimizer | None = None,
    loss_fn: torch.nn.Module | None = None,
) -> tuple[float | None, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    training = optimizer is not None
    model.train(training)
    losses: list[float] = []
    edge_ids: list[Tensor] = []
    labels: list[Tensor] = []
    scores: list[Tensor] = []
    all_logits: list[Tensor] = []

    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for batch_number, batch in enumerate(loader, start=1):
            _ensure_seed_edges(batch, loader.data, supervised_positions)
            if ego_ids:
                _add_ego_ids(batch)
            mask, selected_ids = _seed_mask(batch, supervised_positions)
            mask = mask.to(device)
            batch = batch.to(device)
            logits = model(batch)[mask]
            truth = batch[FORWARD].y[mask]
            if training:
                assert optimizer is not None and loss_fn is not None
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(logits, truth)
                loss.backward()
                optimizer.step()
                losses.append(float(loss.detach().cpu()))
            edge_ids.append(selected_ids)
            labels.append(truth.detach().cpu())
            scores.append(torch.softmax(logits.detach(), dim=-1)[:, 1].cpu())
            all_logits.append(logits.detach().cpu())
            if training and batch_number % 50 == 0:
                print(f"  training batches: {batch_number}/{len(loader)}", flush=True)

    ids_np = torch.cat(edge_ids).numpy()
    labels_np = torch.cat(labels).numpy()
    scores_np = torch.cat(scores).numpy()
    logits_np = torch.cat(all_logits).numpy()
    order = np.argsort(ids_np, kind="stable")
    mean_loss = float(np.mean(losses)) if losses else None
    return mean_loss, ids_np[order], labels_np[order], scores_np[order], logits_np[order]


def evaluate(
    model: MegaPna,
    loader: LinkNeighborLoader,
    supervised_positions: Tensor,
    device: torch.device,
    *,
    ego_ids: bool,
    threshold: float = 0.5,
) -> EvaluationOutput:
    _, edge_ids, labels, scores, logits = _collect(
        model,
        loader,
        supervised_positions,
        device,
        ego_ids=ego_ids,
    )
    metrics = paper_binary_metrics(labels, logits)
    metrics["softmax_pr_auc"] = binary_metrics(labels, scores, threshold=threshold)["pr_auc"]
    return EvaluationOutput(metrics, edge_ids, labels, scores, logits)


def _save_checkpoint(
    path: Path,
    model: MegaPna,
    optimizer: torch.optim.Optimizer,
    *,
    epoch: int,
    seed: int,
    config: MegaPnaConfig,
    feature_names: tuple[str, ...],
    split: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema_version": "fin07.mega_pna.checkpoint.v1",
            "epoch": epoch,
            "seed": seed,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "node_degree_hist": model.node_degree_hist.detach().cpu(),
            "edge_degree_hist": model.edge_degree_hist.detach().cpu(),
            "config": config.to_dict(),
            "feature_names": list(feature_names),
            "split": split,
        },
        path,
    )


def train_one_seed(
    bundle: MegaPnaDataBundle,
    *,
    config: MegaPnaConfig,
    seed: int,
    device_name: str = "auto",
    checkpoint_path: Path | None = None,
    predictions_path: Path | None = None,
) -> dict[str, object]:
    config.validate()
    preflight_neighbor_sampler()
    set_seed(seed)
    device = resolve_device(device_name)
    loaders = make_loaders(bundle, config)
    sample = next(iter(loaders["train"]))
    if config.ego_ids:
        _add_ego_ids(sample)
    model = _model_from_sample(sample, config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(
            [config.class_weight_clean, config.class_weight_laundering],
            dtype=torch.float32,
            device=device,
        )
    )
    started = time.perf_counter()
    best_validation_f1 = -1.0
    best_epoch = 0
    best_state: dict[str, Tensor] | None = None
    history: list[dict[str, object]] = []
    train_positions = bundle.split.positions("train")
    validation_positions = bundle.split.positions("validation")
    test_positions = bundle.split.positions("test")

    for epoch in range(1, config.epochs + 1):
        loss, _, train_labels, train_scores, train_logits = _collect(
            model,
            loaders["train"],
            train_positions,
            device,
            ego_ids=config.ego_ids,
            optimizer=optimizer,
            loss_fn=loss_fn,
        )
        validation = evaluate(
            model,
            loaders["validation"],
            validation_positions,
            device,
            ego_ids=config.ego_ids,
        )
        train_metrics = paper_binary_metrics(train_labels, train_logits)
        train_metrics["softmax_pr_auc"] = binary_metrics(train_labels, train_scores)["pr_auc"]
        row = {
            "epoch": epoch,
            "loss": loss,
            "train": train_metrics,
            "validation": validation.metrics,
        }
        history.append(row)
        validation_f1 = float(validation.metrics["f1"])
        print(
            f"seed={seed} epoch={epoch:03d} loss={loss:.6f} "
            f"train_f1={train_metrics['f1']:.4f} val_f1={validation_f1:.4f}",
            flush=True,
        )
        if validation_f1 > best_validation_f1:
            best_validation_f1 = validation_f1
            best_epoch = epoch
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
            if checkpoint_path is not None:
                _save_checkpoint(
                    checkpoint_path,
                    model,
                    optimizer,
                    epoch=epoch,
                    seed=seed,
                    config=config,
                    feature_names=bundle.feature_names,
                    split=bundle.split.to_dict(),
                )

    if best_state is None:
        raise RuntimeError("Training did not produce a checkpoint")
    model.load_state_dict(best_state)
    validation = evaluate(
        model,
        loaders["validation"],
        validation_positions,
        device,
        ego_ids=config.ego_ids,
    )
    operational_threshold = best_f1_threshold(validation.labels, validation.scores)
    test_paper = evaluate(
        model,
        loaders["test"],
        test_positions,
        device,
        ego_ids=config.ego_ids,
    )
    test_operational = binary_metrics(
        test_paper.labels,
        test_paper.scores,
        threshold=operational_threshold,
    )
    budgets = [100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000]
    report: dict[str, object] = {
        "schema_version": "fin07.mega_pna.seed_result.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "device": str(device),
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "config": config.to_dict(),
        "feature_names": list(bundle.feature_names),
        "split": bundle.split.to_dict(),
        "best_epoch": best_epoch,
        "validation_at_best": validation.metrics,
        "test_paper_protocol": test_paper.metrics,
        "test_validation_threshold": test_operational,
        "operational_budget": budget_metrics(test_paper.labels, test_paper.scores, budgets),
        "seconds": time.perf_counter() - started,
        "history": history,
    }
    if predictions_path is not None:
        predictions_path.parent.mkdir(parents=True, exist_ok=True)
        pd_frame = {
            "edge_position": test_paper.edge_ids,
            "source_edge_id": bundle.source_edge_ids[test_paper.edge_ids].numpy(),
            "is_laundering": test_paper.labels,
            "score": test_paper.scores,
        }
        import pandas as pd

        pd.DataFrame(pd_frame).to_parquet(predictions_path, index=False)
        report["predictions_path"] = str(predictions_path)
    return report


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
