"""Configuration and evidence/parameter registry loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARAMETER_DIR = ROOT / "abm" / "parameters"
SOURCE_REGISTRY_PATH = ROOT / "abm" / "sources" / "source_registry.yaml"


@dataclass(frozen=True)
class SimulationConfig:
    dataset_id: str
    dataset_version: str
    schema_version: str
    simulation_seed: int
    simulation_start: datetime
    simulation_end: datetime
    customer_count: int
    merchant_count: int
    currency: str
    scenario_scale: float
    hard_negative_scale: float
    release_owner: str
    parameter_registry_version: str
    source_registry_version: str
    parquet_compression: str
    transaction_partition: str

    @classmethod
    def load(cls, path: str | Path) -> SimulationConfig:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        config = cls(
            dataset_id=str(raw["dataset_id"]),
            dataset_version=str(raw["dataset_version"]),
            schema_version=str(raw["schema_version"]),
            simulation_seed=int(raw["simulation_seed"]),
            simulation_start=_parse_datetime(raw["simulation_start"]),
            simulation_end=_parse_datetime(raw["simulation_end"]),
            customer_count=int(raw["customer_count"]),
            merchant_count=int(raw["merchant_count"]),
            currency=str(raw["currency"]),
            scenario_scale=float(raw["scenario_scale"]),
            hard_negative_scale=float(raw["hard_negative_scale"]),
            release_owner=str(raw["release_owner"]),
            parameter_registry_version=str(raw["parameter_registry_version"]),
            source_registry_version=str(raw["source_registry_version"]),
            parquet_compression=str(raw["parquet_compression"]),
            transaction_partition=str(raw["transaction_partition"]),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.dataset_id != "ABM-BANK":
            raise ValueError("dataset_id must be ABM-BANK")
        if self.simulation_end <= self.simulation_start:
            raise ValueError("simulation_end must be after simulation_start")
        if self.customer_count < 1:
            raise ValueError("customer_count must be positive")
        if self.merchant_count < 1:
            raise ValueError("merchant_count must be positive")
        if not 0 < self.scenario_scale <= 10:
            raise ValueError("scenario_scale must be in (0, 10]")
        if not 0 < self.hard_negative_scale <= 10:
            raise ValueError("hard_negative_scale must be in (0, 10]")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-4217-style code")
        if self.transaction_partition not in {"month", "day"}:
            raise ValueError("transaction_partition must be month or day")

    @property
    def release_name(self) -> str:
        return f"{self.dataset_id}-v{self.dataset_version}"

    @property
    def duration_days(self) -> int:
        return (self.simulation_end.date() - self.simulation_start.date()).days + 1

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "schema_version": self.schema_version,
            "simulation_seed": self.simulation_seed,
            "simulation_start": self.simulation_start.isoformat(),
            "simulation_end": self.simulation_end.isoformat(),
            "customer_count": self.customer_count,
            "merchant_count": self.merchant_count,
            "currency": self.currency,
            "scenario_scale": self.scenario_scale,
            "hard_negative_scale": self.hard_negative_scale,
            "release_owner": self.release_owner,
            "parameter_registry_version": self.parameter_registry_version,
            "source_registry_version": self.source_registry_version,
            "parquet_compression": self.parquet_compression,
            "transaction_partition": self.transaction_partition,
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class ParameterRegistry:
    """Validated, immutable view over all parameter cards."""

    REQUIRED_FIELDS = {
        "parameter_id",
        "description",
        "value",
        "source_ids",
        "derivation_method",
        "assumption",
        "confidence",
        "sensitivity_range",
        "effect_on_simulation",
        "reason",
    }

    def __init__(
        self,
        parameter_dir: Path = PARAMETER_DIR,
        source_registry_path: Path = SOURCE_REGISTRY_PATH,
    ) -> None:
        self.parameter_dir = parameter_dir
        self.source_registry_path = source_registry_path
        self.sources = self._load_sources()
        self.cards: dict[str, dict[str, Any]] = {}
        self.registry_versions: set[str] = set()
        self._load_parameters()
        self.validate()

    def _load_sources(self) -> dict[str, dict[str, Any]]:
        raw = yaml.safe_load(self.source_registry_path.read_text(encoding="utf-8"))
        return {str(card["source_id"]): card for card in raw["sources"]}

    def _load_parameters(self) -> None:
        paths = sorted(self.parameter_dir.glob("*.yaml"))
        if not paths:
            raise ValueError(f"no parameter files found in {self.parameter_dir}")
        for path in paths:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.registry_versions.add(str(raw["registry_version"]))
            for card in raw["parameters"]:
                parameter_id = str(card["parameter_id"])
                if parameter_id in self.cards:
                    raise ValueError(f"duplicate parameter_id {parameter_id}")
                card = dict(card)
                card["simulation_component"] = str(raw["component"])
                card["registry_file"] = path.name
                self.cards[parameter_id] = card

    def validate(self) -> None:
        if len(self.registry_versions) != 1:
            raise ValueError(f"parameter files disagree on version: {self.registry_versions}")
        errors: list[str] = []
        for parameter_id, card in sorted(self.cards.items()):
            missing = self.REQUIRED_FIELDS - card.keys()
            if missing:
                errors.append(f"{parameter_id} missing {sorted(missing)}")
            if card.get("confidence") not in {"high", "medium", "low"}:
                errors.append(f"{parameter_id} has invalid confidence")
            if not isinstance(card.get("assumption"), bool):
                errors.append(f"{parameter_id} assumption must be boolean")
            for source_id in card.get("source_ids", []):
                if source_id not in self.sources:
                    errors.append(f"{parameter_id} references unknown source {source_id}")
            if card.get("assumption") and not card.get("reason"):
                errors.append(f"{parameter_id} assumption requires reason")
            if not card.get("assumption") and not card.get("source_ids") and not card.get("reason"):
                errors.append(f"{parameter_id} needs evidence or policy reason")
        if errors:
            raise ValueError("invalid parameter registry:\n- " + "\n- ".join(errors))

    @property
    def version(self) -> str:
        return next(iter(self.registry_versions))

    def card(self, parameter_id: str) -> dict[str, Any]:
        try:
            return self.cards[parameter_id]
        except KeyError as exc:
            raise KeyError(f"unregistered simulation parameter: {parameter_id}") from exc

    def value(self, parameter_id: str) -> Any:
        return self.card(parameter_id)["value"]

    def fingerprint(self) -> str:
        payload = [
            {key: value for key, value in sorted(card.items()) if key != "registry_file"}
            for _, card in sorted(self.cards.items())
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        raise ValueError(f"datetime requires timezone: {value}")
    return result
