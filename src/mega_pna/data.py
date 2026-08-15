from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import torch
from torch import Tensor
from torch_geometric.data import HeteroData

DATASETS = {
    "Small_HI": "HI-Small_Trans.csv",
    "Small_LI": "LI-Small_Trans.csv",
    "Medium_HI": "HI-Medium_Trans.csv",
}
PAPER_FEATURES = ("Timestamp", "Amount Received", "Received Currency", "Payment Format")


@dataclass(frozen=True)
class TemporalSplit:
    train_end: int
    validation_end: int
    total: int
    train_days: tuple[int, ...]
    validation_days: tuple[int, ...]
    test_days: tuple[int, ...]

    def positions(self, name: str) -> Tensor:
        if name == "train":
            return torch.arange(0, self.train_end)
        if name == "validation":
            return torch.arange(self.train_end, self.validation_end)
        if name == "test":
            return torch.arange(self.validation_end, self.total)
        raise KeyError(name)

    def to_dict(self) -> dict[str, object]:
        return {
            "train_end": self.train_end,
            "validation_end": self.validation_end,
            "total": self.total,
            "train_days": list(self.train_days),
            "validation_days": list(self.validation_days),
            "test_days": list(self.test_days),
        }


@dataclass
class MegaPnaDataBundle:
    train: HeteroData
    validation: HeteroData
    test: HeteroData
    split: TemporalSplit
    feature_names: tuple[str, ...]
    labels: Tensor
    source_edge_ids: Tensor


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def format_kaggle_file(raw_path: Path, output_path: Path, *, force: bool = False) -> dict:
    """Produce the exact ten-column MEGA-GNN AML data contract.

    The official formatter depends on ``datatable``, which has no Python 3.14
    build. This DuckDB implementation preserves its observable rules: all input
    columns are strings, bank leading zeros and self-transfers are retained,
    categorical/account IDs follow first occurrence, EdgeID is the source-row
    index, timestamps are seconds from ten seconds before the first midnight,
    and output is sorted by timestamp.
    """

    raw_path = raw_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists() and not force:
        manifest_path = output_path.with_suffix(".manifest.json")
        if not manifest_path.exists():
            raise FileExistsError(f"{output_path} exists without its manifest; inspect it and rerun with --force")
        return json.loads(manifest_path.read_text())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_input = str(raw_path).replace("'", "''")
    escaped_output = str(output_path).replace("'", "''")
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=true")
    con.execute("SET TimeZone='UTC'")
    con.execute(
        f"""
        CREATE TEMP TABLE raw AS
        SELECT row_number() OVER () - 1 AS edge_id, *
        FROM read_csv('{escaped_input}', all_varchar=true, header=true)
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE accounts AS
        WITH appearances AS (
            SELECT "From Bank" || "Account" AS value, edge_id * 2 AS position FROM raw
            UNION ALL
            SELECT "To Bank" || "Account_1", edge_id * 2 + 1 FROM raw
        ), first_seen AS (
            SELECT value, min(position) AS position FROM appearances GROUP BY value
        )
        SELECT value, row_number() OVER (ORDER BY position) - 1 AS id FROM first_seen
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE currencies AS
        WITH appearances AS (
            SELECT "Receiving Currency" AS value, edge_id * 2 AS position FROM raw
            UNION ALL
            SELECT "Payment Currency", edge_id * 2 + 1 FROM raw
        ), first_seen AS (
            SELECT value, min(position) AS position FROM appearances GROUP BY value
        )
        SELECT value, row_number() OVER (ORDER BY position) - 1 AS id FROM first_seen
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE payment_formats AS
        WITH first_seen AS (
            SELECT "Payment Format" AS value, min(edge_id) AS position
            FROM raw GROUP BY "Payment Format"
        )
        SELECT value, row_number() OVER (ORDER BY position) - 1 AS id FROM first_seen
        """
    )
    con.execute(
        f"""
        COPY (
            WITH parsed AS (
                SELECT *, strptime("Timestamp", '%Y/%m/%d %H:%M') AS parsed_ts
                FROM raw
            ), origin AS (
                SELECT date_trunc('day', parsed_ts) - INTERVAL 10 SECOND AS first_ts
                FROM parsed ORDER BY edge_id LIMIT 1
            )
            SELECT
                r.edge_id AS EdgeID,
                fa.id AS from_id,
                ta.id AS to_id,
                date_diff('second', o.first_ts, r.parsed_ts) AS Timestamp,
                CAST(r."Amount Paid" AS DOUBLE) AS "Amount Sent",
                pc.id AS "Sent Currency",
                CAST(r."Amount Received" AS DOUBLE) AS "Amount Received",
                rc.id AS "Received Currency",
                pf.id AS "Payment Format",
                CAST(r."Is Laundering" AS INTEGER) AS "Is Laundering"
            FROM parsed r
            CROSS JOIN origin o
            JOIN accounts fa ON fa.value = r."From Bank" || r."Account"
            JOIN accounts ta ON ta.value = r."To Bank" || r."Account_1"
            JOIN currencies pc ON pc.value = r."Payment Currency"
            JOIN currencies rc ON rc.value = r."Receiving Currency"
            JOIN payment_formats pf ON pf.value = r."Payment Format"
            ORDER BY Timestamp, EdgeID
        ) TO '{escaped_output}' (HEADER, DELIMITER ',')
        """
    )
    stats = con.execute(
        """
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE "From Bank" || "Account" = "To Bank" || "Account_1") AS self_transfers,
               sum(CAST("Is Laundering" AS BIGINT)) AS positives,
               count(DISTINCT "Receiving Currency") AS receiving_currencies,
               count(DISTINCT "Payment Format") AS payment_formats
        FROM raw
        """
    ).fetchone()
    con.close()
    manifest = {
        "schema_version": "fin07.mega_pna.formatted.v1",
        "source": str(raw_path),
        "source_sha256": sha256_file(raw_path),
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "rows": int(stats[0]),
        "self_transfers": int(stats[1]),
        "positives": int(stats[2]),
        "receiving_currencies": int(stats[3]),
        "payment_formats": int(stats[4]),
        "contract_columns": [
            "EdgeID",
            "from_id",
            "to_id",
            "Timestamp",
            "Amount Sent",
            "Sent Currency",
            "Amount Received",
            "Received Currency",
            "Payment Format",
            "Is Laundering",
        ],
    }
    output_path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def temporal_split(timestamps: np.ndarray) -> TemporalSplit:
    """Match the official day-boundary split closest to 60/20/20 by row count."""

    if timestamps.ndim != 1 or timestamps.size == 0:
        raise ValueError("timestamps must be a non-empty vector")
    days = np.floor(timestamps / 86_400).astype(np.int64)
    n_days = int(days.max()) + 1
    totals = np.bincount(days, minlength=n_days)
    target = (0.6, 0.2, 0.2)
    best: tuple[float, int, int] | None = None
    for first in range(1, n_days - 1):
        for second in range(first + 1, n_days):
            counts = (totals[:first].sum(), totals[first:second].sum(), totals[second:].sum())
            proportions = tuple(value / timestamps.size for value in counts)
            error = max(abs(value - wanted) / wanted for value, wanted in zip(proportions, target))
            candidate = (error, first, second)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise ValueError("The paper protocol needs transactions spanning at least three days")
    _, first, second = best
    train_end = int(totals[:first].sum())
    validation_end = int(totals[:second].sum())
    return TemporalSplit(
        train_end=train_end,
        validation_end=validation_end,
        total=int(timestamps.size),
        train_days=tuple(range(first)),
        validation_days=tuple(range(first, second)),
        test_days=tuple(range(second, n_days)),
    )


def _z_normalize(values: Tensor) -> Tensor:
    std = values.std(dim=0, keepdim=True)
    std = torch.where(std == 0, torch.ones_like(std), std)
    return (values - values.mean(dim=0, keepdim=True)) / std


def _graph(
    edge_index: Tensor,
    raw_edge_attr: Tensor,
    labels: Tensor,
    timestamps: Tensor,
    *,
    end: int,
    num_nodes: int,
) -> HeteroData:
    data = HeteroData()
    data["node"].x = torch.ones((num_nodes, 1), dtype=torch.float32)
    index = edge_index[:, :end]
    attrs = _z_normalize(raw_edge_attr[:end])
    edge_ids = torch.arange(end, dtype=torch.long)
    forward = ("node", "to", "node")
    reverse = ("node", "rev_to", "node")
    data[forward].edge_index = index
    data[forward].edge_attr = attrs
    data[forward].y = labels[:end]
    data[forward].edge_id = edge_ids
    data[forward].timestamps = timestamps[:end]
    data[reverse].edge_index = index.flip(0)
    data[reverse].edge_attr = attrs.clone()
    data[reverse].edge_id = edge_ids.clone()
    data[reverse].timestamps = timestamps[:end].clone()
    return data


def load_formatted_data(path: Path, *, include_payment_format: bool = True) -> MegaPnaDataBundle:
    feature_names = PAPER_FEATURES if include_payment_format else PAPER_FEATURES[:-1]
    columns = ["EdgeID", "from_id", "to_id", *feature_names, "Is Laundering"]
    frame = pd.read_csv(
        path,
        usecols=columns,
        dtype={
            "from_id": "int64",
            "to_id": "int64",
            "EdgeID": "int64",
            "Timestamp": "float32",
            "Amount Received": "float32",
            "Received Currency": "float32",
            "Payment Format": "float32",
            "Is Laundering": "int64",
        },
    )
    timestamps_np = frame["Timestamp"].to_numpy(dtype=np.float64, copy=False)
    split = temporal_split(timestamps_np)
    edge_index = torch.from_numpy(frame[["from_id", "to_id"]].to_numpy(dtype=np.int64).T.copy())
    edge_attr = torch.from_numpy(frame[list(feature_names)].to_numpy(dtype=np.float32, copy=True))
    labels = torch.from_numpy(frame["Is Laundering"].to_numpy(dtype=np.int64, copy=True))
    source_edge_ids = torch.from_numpy(frame["EdgeID"].to_numpy(dtype=np.int64, copy=True))
    timestamps = torch.from_numpy(timestamps_np.astype(np.float32, copy=True))
    num_nodes = int(edge_index.max()) + 1
    return MegaPnaDataBundle(
        train=_graph(
            edge_index,
            edge_attr,
            labels,
            timestamps,
            end=split.train_end,
            num_nodes=num_nodes,
        ),
        validation=_graph(
            edge_index,
            edge_attr,
            labels,
            timestamps,
            end=split.validation_end,
            num_nodes=num_nodes,
        ),
        test=_graph(
            edge_index,
            edge_attr,
            labels,
            timestamps,
            end=split.total,
            num_nodes=num_nodes,
        ),
        split=split,
        feature_names=feature_names,
        labels=labels,
        source_edge_ids=source_edge_ids,
    )
