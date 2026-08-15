import ast
from pathlib import Path

import yaml

from src.observability.redaction import sanitize

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_METRIC_LABELS = {
    "account_id",
    "account_key",
    "transaction_id",
    "alert_id",
    "case_id",
    "investigation_id",
    "request_id",
    "trace_id",
    "span_id",
    "job_id",
    "tool_call_id",
    "customer_name",
}


def _metric_attr_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not isinstance(owner, ast.Attribute) or not isinstance(owner.value, ast.Name):
            continue
        if owner.value.id != "METRICS":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name) and argument.func.id == "attrs":
                yield argument


def test_metric_dimensions_do_not_contain_dynamic_ids() -> None:
    violations: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _metric_attr_calls(tree):
            for keyword in call.keywords:
                if keyword.arg in FORBIDDEN_METRIC_LABELS:
                    violations.append(f"{path.relative_to(ROOT)}:{call.lineno}:{keyword.arg}")
    assert not violations, "High-cardinality metric labels are forbidden: " + ", ".join(violations)


def test_redaction_is_recursive_and_preserves_safe_metadata() -> None:
    value = {
        "authorization": "Bearer secret",
        "nested": {"account_number": "123", "duration_ms": 12},
        "api_key_hint": "key",
    }
    redacted = sanitize(value)
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["account_number"] == "[REDACTED]"
    assert redacted["nested"]["duration_ms"] == 12
    assert redacted["api_key_hint"] == "[REDACTED]"


def test_collector_has_separate_signal_pipelines_and_redaction() -> None:
    config = yaml.safe_load((ROOT / "monitoring/otel-collector/config.yaml").read_text(encoding="utf-8"))
    pipelines = config["service"]["pipelines"]
    assert set(pipelines) == {"traces", "metrics", "logs"}
    assert "attributes/redact" in pipelines["traces"]["processors"]
    assert "attributes/redact" in pipelines["logs"]["processors"]
    assert pipelines["logs"]["exporters"] == ["otlp_http/loki"]
    assert pipelines["traces"]["exporters"] == ["otlp_grpc/jaeger"]


def test_single_dashboard_is_correlated_and_question_driven() -> None:
    import json

    paths = list((ROOT / "monitoring/grafana/dashboards").glob("*.json"))
    assert [path.name for path in paths] == ["fin07-observability.json"]
    dashboard = json.loads(paths[0].read_text(encoding="utf-8"))
    assert dashboard["uid"] == "fin07-observability"
    assert dashboard["title"] == "FIN-07 — Tổng quan vận hành"
    assert len(dashboard["panels"]) == 6
    assert {panel["datasource"]["type"] for panel in dashboard["panels"]} == {"prometheus"}
    assert dashboard["templating"]["list"] == []
    for panel in dashboard["panels"]:
        assert panel.get("description"), f"panel {panel.get('title')} has no operational question"

    cockpit = (ROOT / "web/src/components/observability/GrafanaCockpit.tsx").read_text(encoding="utf-8")
    assert 'type CockpitView = "overview" | "logs" | "traces"' in cockpit
    assert 'type: "loki", uid: "loki"' in cockpit
    assert 'type: "jaeger", uid: "jaeger"' in cockpit
    assert "/grafana/explore?" in cockpit
