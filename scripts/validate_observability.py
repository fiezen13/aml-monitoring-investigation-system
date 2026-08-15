#!/usr/bin/env python3
"""Offline validation for CI; no live telemetry backends are required."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    yaml_files = [
        ROOT / "monitoring/otel-collector/config.yaml",
        ROOT / "monitoring/loki/config.yaml",
        ROOT / "monitoring/prometheus/prometheus.yml",
        ROOT / "monitoring/prometheus/rules/fin07.yml",
        ROOT / "monitoring/grafana/provisioning/datasources/prometheus.yml",
        ROOT / "monitoring/grafana/provisioning/dashboards/default.yml",
    ]
    for path in yaml_files:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    dashboards = list((ROOT / "monitoring/grafana/dashboards").glob("*.json"))
    if [path.name for path in dashboards] != ["fin07-observability.json"]:
        raise RuntimeError("Exactly one Grafana dashboard, fin07-observability.json, must be provisioned")
    document = json.loads(dashboards[0].read_text(encoding="utf-8"))
    if document.get("uid") != "fin07-observability":
        raise RuntimeError("The embedded dashboard UID must remain fin07-observability")
    datasource_types = {panel.get("datasource", {}).get("type") for panel in document.get("panels", [])}
    if datasource_types != {"prometheus"} or len(document.get("panels", [])) != 6:
        raise RuntimeError("The overview must remain a focused six-panel Prometheus dashboard")
    if document.get("templating", {}).get("list"):
        raise RuntimeError("Overview filters belong in focused investigation views, not the main dashboard")
    if any(not panel.get("description") for panel in document.get("panels", [])):
        raise RuntimeError("Every cockpit panel must state its operational question")
    cockpit = (ROOT / "web/src/components/observability/GrafanaCockpit.tsx").read_text(encoding="utf-8")
    for required in ('"overview" | "logs" | "traces"', 'uid: "loki"', 'uid: "jaeger"', "/grafana/explore?"):
        if required not in cockpit:
            raise RuntimeError(f"Focused logs/traces integration is missing {required}")
    print(f"validated {len(yaml_files)} YAML files and {len(dashboards)} dashboards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
