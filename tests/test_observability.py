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


DASHBOARD_ROWS = {
    "fin07-observability.json": (
        "fin07-observability",
        ["Latency", "Traffic", "Error", "Cost", "Tokens", "Quality"],
    ),
    "fin07-system.json": (
        "fin07-system",
        [
            "Sức khoẻ",
            "Độ trễ API",
            "Lưu lượng và lỗi",
            "Hàng đợi và worker",
            "Điều tra đầu-cuối",
            "Hạ tầng",
        ],
    ),
}


def _dashboards() -> dict:
    import json

    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "monitoring/grafana/dashboards").glob("*.json"))
    }


def test_dashboards_are_correlated_and_question_driven() -> None:
    boards = _dashboards()
    assert sorted(boards) == sorted(DASHBOARD_ROWS)
    for name, document in boards.items():
        uid, expected_rows = DASHBOARD_ROWS[name]
        assert document["uid"] == uid
        # Mỗi nhóm là một hàng, không hơn không kém.
        rows = [panel for panel in document["panels"] if panel["type"] == "row"]
        assert [row["title"].split(" · ")[1] for row in rows] == expected_rows, name
        charts = [panel for panel in document["panels"] if panel["type"] != "row"]
        assert {panel["datasource"]["type"] for panel in charts} == {"prometheus"}, name
        for panel in charts:
            assert panel.get("description"), f"{name}: panel {panel.get('title')} has no operational question"
            assert panel.get("targets"), f"{name}: panel {panel.get('title')} has no query"


def test_system_dashboard_shows_real_system_latency_not_only_agent_metrics() -> None:
    """Bảng Hệ thống phải vẽ độ trễ CỦA HỆ THỐNG, không phải độ trễ gọi mô hình.

    Trước đây chỉ có bảng tác tử: hàng tên là "Latency" nhưng mọi truy vấn đều
    hỏi `fin07_gemini_*`, nên nhìn vào không biết API nhanh hay chậm. Test này
    khoá lại đúng điều đó — độ trễ HTTP, hàng đợi worker và thời gian điều tra
    đầu-cuối đều phải có mặt, và không được lẫn chỉ số Gemini vào.
    """
    document = _dashboards()["fin07-system.json"]
    exprs = " ".join(target.get("expr", "") for panel in document["panels"] for target in panel.get("targets", []))
    for metric in (
        "fin07_http_request_duration_seconds_bucket",  # độ trễ API thật
        "fin07_http_requests_total",
        "fin07_worker_queue_wait_seconds_bucket",  # chờ hàng đợi
        "fin07_worker_job_duration_seconds_bucket",
        "fin07_investigation_duration_seconds_bucket",  # đầu-cuối nghiệp vụ
    ):
        assert metric in exprs, f"bảng Hệ thống không vẽ {metric}"
    assert "fin07_gemini" not in exprs, "chỉ số Gemini thuộc bảng Tác tử, không phải bảng Hệ thống"

    # Nhãn `job` của worker bị Prometheus đổi tên vì trùng nhãn scrape. Gom theo
    # `job` sẽ ra tên scrape chứ không phải loại tác vụ — sai âm thầm.
    assert "exported_job" in exprs


def test_dashboard_queries_only_use_metrics_the_code_emits() -> None:
    """Không panel nào được hỏi một chỉ số fin07_* mà mã không hề tạo ra.

    Panel trỏ sai tên không báo lỗi, nó chỉ hiện đường trống — và người xem hiểu
    nhầm là hệ thống đang im. Danh sách chỉ số lấy thẳng từ nơi khai báo.
    """
    import re

    source = (ROOT / "src/observability/metrics.py").read_text(encoding="utf-8")
    declared = {name.replace(".", "_") for name in re.findall(r'create_\w+\(\s*"([^"]+)"', source)}
    assert declared, "không đọc được chỉ số nào từ src/observability/metrics.py"

    used = set()
    for document in _dashboards().values():
        for panel in document["panels"]:
            for target in panel.get("targets", []):
                used |= set(re.findall(r"\bfin07_[a-z0-9_]+", target.get("expr", "")))

    unknown = set()
    for name in used:
        base = name
        for suffix in ("_bucket", "_sum", "_count", "_total"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        if base not in declared and name not in declared:
            unknown.add(name)
    assert not unknown, f"biểu đồ hỏi chỉ số không tồn tại: {sorted(unknown)}"

    # Kiến trúc trình bày MỚI: Grafana CHỈ để trực quan hoá metrics; Logs và
    # Traces là giao diện GỐC đọc thẳng lượt chạy tác tử (không nhúng Grafana
    # Explore/Loki/Jaeger ở tầng giao diện nữa — tầng collector vẫn xuất đi Loki/
    # Jaeger, kiểm ở test phía trên).
    panel = (ROOT / "web/src/components/observability/ObservabilityPanel.tsx").read_text(encoding="utf-8")
    assert 'type Tab = "metrics" | "logs" | "traces"' in panel
    assert "GRAFANA_BOARDS" in panel  # tab metrics chuyển được giữa bảng Hệ thống và bảng Tác tử
    assert "api.agentRuns" in panel  # logs/traces gốc, đọc lượt chạy tác tử
