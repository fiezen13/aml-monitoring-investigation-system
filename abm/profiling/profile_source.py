"""Profile CSV or Parquet inputs without treating observations as ground truth."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq


def profile_source(
    source: str | Path,
    *,
    source_id: str,
    source_column: str | None = None,
    target_column: str | None = None,
    time_column: str | None = None,
) -> dict[str, Any]:
    path = Path(source)
    table = _read_table(path)
    rows = table.to_pylist()
    if not rows:
        raise ValueError(f"source is empty: {path}")
    columns: dict[str, Any] = {}
    for field in table.schema:
        values = [row[field.name] for row in rows]
        non_null = [value for value in values if value is not None]
        item: dict[str, Any] = {
            "arrow_type": str(field.type),
            "null_count": len(values) - len(non_null),
            "null_rate": (len(values) - len(non_null)) / len(values),
            "distinct_count": len({_hashable(value) for value in non_null}),
        }
        if non_null and pa.types.is_numeric(field.type):
            numbers = [float(value) for value in non_null]
            ordered = sorted(numbers)
            item["numeric"] = {
                "min": ordered[0],
                "p25": _quantile(ordered, 0.25),
                "median": _quantile(ordered, 0.5),
                "p75": _quantile(ordered, 0.75),
                "max": ordered[-1],
                "mean": mean(numbers),
                "standard_deviation": pstdev(numbers),
                "p95": _quantile(ordered, 0.95),
                "p99": _quantile(ordered, 0.99),
                "tail_ratio_p99_to_median": _quantile(ordered, 0.99) / max(abs(_quantile(ordered, 0.5)), 1e-12),
                "positive_log_mean": mean(math.log1p(value) for value in numbers if value >= 0)
                if any(value >= 0 for value in numbers)
                else None,
            }
        elif non_null and (pa.types.is_string(field.type) or pa.types.is_boolean(field.type) or len(non_null) <= 100):
            counts = Counter(str(value) for value in non_null)
            item["top_values"] = [
                {"value": value, "count": count, "rate": count / len(non_null)}
                for value, count in counts.most_common(20)
            ]
            probabilities = [count / len(non_null) for count in counts.values()]
            item["categorical"] = {
                "entropy_nats": -sum(probability * math.log(probability) for probability in probabilities),
                "rare_category_count": sum(count / len(non_null) < 0.01 for count in counts.values()),
            }
        if non_null and (pa.types.is_timestamp(field.type) or pa.types.is_date(field.type)):
            item["temporal"] = {
                "min": min(non_null).isoformat(),
                "max": max(non_null).isoformat(),
            }
        columns[field.name] = item

    temporal = None
    if time_column:
        _require_columns(table, [time_column])
        timestamps = [row[time_column] for row in rows if row[time_column] is not None]
        timestamps.sort()
        by_day = Counter(_as_date(value).isoformat() for value in timestamps)
        by_hour = Counter(value.hour if isinstance(value, datetime) else 0 for value in timestamps)
        interarrival = [
            (right - left).total_seconds()
            for left, right in zip(timestamps, timestamps[1:])
            if isinstance(left, datetime) and isinstance(right, datetime)
        ]
        interarrival_mean = mean(interarrival) if interarrival else None
        interarrival_std = pstdev(interarrival) if interarrival else None
        temporal = {
            "column": time_column,
            "first": min(timestamps).isoformat(),
            "last": max(timestamps).isoformat(),
            "daily_counts": dict(sorted(by_day.items())),
            "hourly_counts": {str(key): value for key, value in sorted(by_hour.items())},
            "weekday_count": sum(_as_date(value).weekday() < 5 for value in timestamps),
            "weekend_count": sum(_as_date(value).weekday() >= 5 for value in timestamps),
            "interarrival_seconds": {
                "count": len(interarrival),
                "mean": interarrival_mean,
                "median": _quantile(sorted(interarrival), 0.5) if interarrival else None,
                "p95": _quantile(sorted(interarrival), 0.95) if interarrival else None,
                "burstiness": ((interarrival_std - interarrival_mean) / (interarrival_std + interarrival_mean))
                if interarrival and (interarrival_std + interarrival_mean)
                else None,
            },
        }

    graph = None
    if bool(source_column) != bool(target_column):
        raise ValueError("source_column and target_column must be supplied together")
    if source_column and target_column:
        _require_columns(table, [source_column, target_column])
        edges = [
            (str(row[source_column]), str(row[target_column]))
            for row in rows
            if row[source_column] is not None and row[target_column] is not None
        ]
        nodes = {node for edge in edges for node in edge}
        in_degree = Counter(target for _, target in edges)
        out_degree = Counter(source for source, _ in edges)
        edge_set = set(edges)
        reciprocal = sum((target, source) in edge_set for source, target in edge_set)
        graph = {
            "source_column": source_column,
            "target_column": target_column,
            "edge_count": len(edges),
            "unique_edge_count": len(set(edges)),
            "node_count": len(nodes),
            "self_loop_count": sum(source == target for source, target in edges),
            "duplicate_edge_rate": 1 - (len(set(edges)) / len(edges)) if edges else 0.0,
            "reciprocity": reciprocal / len(edge_set) if edge_set else 0.0,
            "in_degree": _counter_summary(in_degree),
            "out_degree": _counter_summary(out_degree),
        }
    return {
        "source_id": source_id,
        "path": str(path.resolve()),
        "profiled_at": datetime.now().astimezone().isoformat(),
        "row_count": table.num_rows,
        "column_count": table.num_columns,
        "columns": columns,
        "temporal_profile": temporal,
        "graph_profile": graph,
        "interpretation_warning": "Observed distributions describe this source only and are not automatically population parameters.",
    }


def write_profile(report: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_table(path: Path) -> pa.Table:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pq.read_table(path)
    if suffix in {".csv", ".tsv"}:
        options = pacsv.ParseOptions(delimiter="\t" if suffix == ".tsv" else ",")
        return pacsv.read_csv(path, parse_options=options)
    raise ValueError("supported profiling inputs are .csv, .tsv, and .parquet")


def _require_columns(table: pa.Table, columns: list[str]) -> None:
    missing = set(columns) - set(table.column_names)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    return value


def _quantile(ordered: list[float], probability: float) -> float:
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _counter_summary(values: Counter[str]) -> dict[str, Any]:
    degrees = sorted(values.values())
    return {
        "minimum": degrees[0] if degrees else 0,
        "median": _quantile([float(value) for value in degrees], 0.5) if degrees else 0,
        "mean": mean(degrees) if degrees else 0,
        "maximum": degrees[-1] if degrees else 0,
    }
