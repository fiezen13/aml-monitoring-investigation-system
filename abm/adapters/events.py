"""Convert canonical transaction rows into the Bank View event envelope."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def transaction_to_event(
    row: dict[str, Any],
    *,
    dataset_version: str = "unknown",
    simulation_run_id: str = "unknown",
) -> dict[str, Any]:
    forbidden = {"label", "scenario_instance_id", "network_id", "hidden_intent", "is_laundering"}
    contamination = sorted(set(row) & forbidden)
    if contamination:
        raise ValueError(f"ground-truth fields cannot enter Bank View events: {contamination}")
    debtor_ref = row["source_account_id"] or row["source_counterparty_ref"]
    creditor_ref = row["destination_account_id"] or row["destination_counterparty_ref"]
    data = {
        "schema_version": row["schema_version"],
        "transaction_id": row["transaction_id"],
        "source_refs": [
            {
                "source_system": row["source_system"],
                "source_id": row["source_record_id"],
                "source_id_type": "SYNTHETIC_TRANSACTION_ID",
            }
        ],
        "posting_status": row["status"],
        "event_time": row["event_time"].isoformat(),
        "posting_time": row["posting_time"].isoformat(),
        "ingestion_time": row["available_from"].isoformat(),
        "available_from": row["available_from"].isoformat(),
        "amount": {"amount": format(row["amount"], "f"), "currency": row["currency"]},
        "direction": "DEBIT" if row["source_account_id"] else "CREDIT",
        "debtor": {"account_ref": debtor_ref, "is_internal": row["source_account_id"] is not None},
        "creditor": {"account_ref": creditor_ref, "is_internal": row["destination_account_id"] is not None},
        "channel": row["channel"],
        "transaction_type": row["transaction_type"],
        "quality_flags": row["quality_flags"],
    }
    if row["purpose_text"] is not None:
        data["purpose_text"] = row["purpose_text"]
    if row["merchant_id"] is not None:
        data["merchant"] = {"merchant_id": row["merchant_id"]}
    if row["session_id"] is not None:
        data["session_ref"] = row["session_id"]
    return {
        "specversion": "1.0",
        "type": "bank.transaction.posted.v1",
        "source": f"{row['source_system']}/ABM-BANK-v{dataset_version}",
        "id": row["event_id"],
        "time": row["available_from"].isoformat(),
        "subject": f"transaction/{row['transaction_id']}",
        "datacontenttype": "application/json",
        "dataschema": "https://fin07.local/contracts/events/bank.transaction.posted.v1.schema.json",
        "idempotency_key": row["event_id"],
        "source_offset": f"{simulation_run_id}/{row['source_record_id']}",
        "partition_key": row["transaction_id"],
        "data_class": row["data_class"],
        "data": data,
    }


def iter_release_events(release_dir: str | Path, limit: int | None = None) -> Iterable[dict[str, Any]]:
    emitted = 0
    root = Path(release_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    dataset_version = str(manifest["dataset_version"])
    simulation_run_id = str(manifest.get("logical_dataset_sha256") or manifest.get("logical_world_sha256"))[:24]
    paths = sorted((root / "bank_view" / "transactions").glob("*/part-*.parquet"))
    if not paths:
        paths = sorted(root.glob("shards/shard-*/bank_view/transactions/*/part-*.parquet"))
    if not paths:
        raise FileNotFoundError(f"release contains no transaction Parquet files: {root}")
    for path in paths:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=4096):
            for row in batch.to_pylist():
                yield transaction_to_event(
                    row,
                    dataset_version=dataset_version,
                    simulation_run_id=simulation_run_id,
                )
                emitted += 1
                if limit is not None and emitted >= limit:
                    return


def write_jsonl(events: Iterable[dict[str, Any]], destination: str | Path) -> int:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value
