"""Configurable projection from simulated value movement to Bank View."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

from abm.registry import ParameterRegistry


class ObservationEngine:
    def __init__(self, registry: ParameterRegistry, rng: random.Random) -> None:
        self.rng = rng
        self.device_missing_rate = float(registry.value("OBS_DEVICE_MISSING_001"))
        self.purpose_missing_rate = float(registry.value("OBS_PURPOSE_MISSING_001"))
        self.delays = registry.value("OBS_INGESTION_DELAY_SECONDS_001")

    def available_from(self, event_time: datetime, channel: str) -> datetime:
        if channel == "BATCH":
            family = "BATCH"
        elif channel in {"BRANCH", "ATM"}:
            family = "BRANCH"
        else:
            family = "REALTIME"
        profile = self.delays[family]
        median = float(profile["median"])
        sigma = float(profile["sigma"])
        cap = float(profile["cap"])
        delay = min(cap, self.rng.lognormvariate(math.log(median), sigma))
        return event_time + timedelta(seconds=delay)

    def project_transaction(self, row: dict[str, Any]) -> dict[str, Any]:
        projected = dict(row)
        if projected.get("device_id") and self.rng.random() < self.device_missing_rate:
            projected["device_id"] = None
            projected["session_id"] = None
            projected["quality_flags"] = _append_flag(projected.get("quality_flags"), "FIELD_MASKED")
        if projected.get("purpose_text") and self.rng.random() < self.purpose_missing_rate:
            projected["purpose_text"] = None
            projected["quality_flags"] = _append_flag(projected.get("quality_flags"), "FIELD_MASKED")
        observed_at = self.available_from(projected["event_time"], projected["channel"])
        projected["available_from"] = max(projected["posting_time"], observed_at)
        return projected


def _append_flag(flags: list[str] | None, value: str) -> list[str]:
    result = list(flags or [])
    if value not in result:
        result.append(value)
    return result
