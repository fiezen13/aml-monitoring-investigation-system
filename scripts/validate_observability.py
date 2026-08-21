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

    panels = document.get("panels", [])
    rows = [panel for panel in panels if panel.get("type") == "row"]
    charts = [panel for panel in panels if panel.get("type") != "row"]

    # Sáu nhóm chỉ số là hợp đồng của bảng điều khiển, không phải sở thích trình
    # bày. Ràng buộc theo *nhóm* thay vì theo tổng số panel: thêm một biểu đồ vào
    # nhóm sẵn có là việc thường ngày, còn thêm hoặc bỏ một nhóm thì đổi hẳn câu
    # hỏi mà bảng này trả lời, và phải là một quyết định có chủ đích.
    expected_rows = ["Latency", "Traffic", "Error", "Cost", "Tokens", "Quality"]
    actual_rows = [str(row.get("title", "")).split("·")[-1].strip() for row in rows]
    if actual_rows != expected_rows:
        raise RuntimeError(f"Bảng điều khiển phải giữ đúng sáu nhóm {expected_rows}, đang có {actual_rows}")

    if not charts:
        raise RuntimeError("Sáu nhóm chỉ số nhưng không có biểu đồ nào")

    # Chỉ ràng buộc panel có vẽ dữ liệu. Hàng tiêu đề không có nguồn dữ liệu, và
    # bắt nó khai báo prometheus sẽ là một luật vô nghĩa.
    datasource_types = {(chart.get("datasource") or {}).get("type") for chart in charts}
    if datasource_types != {"prometheus"}:
        raise RuntimeError(f"Mọi biểu đồ phải đọc từ Prometheus, đang thấy {datasource_types}")

    if any(not chart.get("description") for chart in charts):
        missing = [chart.get("title") for chart in charts if not chart.get("description")]
        raise RuntimeError(f"Mỗi biểu đồ phải nêu rõ câu hỏi vận hành nó trả lời; thiếu ở {missing}")

    if any(not chart.get("targets") for chart in charts):
        missing = [chart.get("title") for chart in charts if not chart.get("targets")]
        raise RuntimeError(f"Biểu đồ không có truy vấn là biểu đồ luôn trống; thiếu ở {missing}")
    # Kiến trúc mới (theo yêu cầu sản phẩm): Grafana CHỈ để trực quan hoá metrics;
    # Logs và Traces là giao diện GỐC đọc thẳng lượt chạy tác tử (không nhúng
    # Grafana Explore/Loki/Jaeger nữa). Kiểm đúng ba mặt đó có mặt.
    panel = (ROOT / "web/src/components/observability/ObservabilityPanel.tsx").read_text(encoding="utf-8")
    for required in ('type Tab = "metrics" | "logs" | "traces"', "GRAFANA_OVERVIEW", "api.agentRuns"):
        if required not in panel:
            raise RuntimeError(f"Observability panel thiếu thành phần bắt buộc: {required}")
    print(f"đã kiểm {len(yaml_files)} file YAML, {len(rows)} nhóm chỉ số và {len(charts)} biểu đồ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
