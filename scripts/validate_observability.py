#!/usr/bin/env python3
"""Offline validation for CI; no live telemetry backends are required."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _declared_metric_names() -> set[str]:
    """Tên chỉ số fin07_* mà mã thực sự tạo ra.

    OpenTelemetry đổi dấu chấm thành gạch dưới, và bộ phơi Prometheus thêm hậu
    tố _bucket/_sum/_count cho histogram, _total cho counter. Ở đây chỉ giữ phần
    gốc; hậu tố được cắt ở chỗ đối chiếu.
    """
    source = (ROOT / "src/observability/metrics.py").read_text(encoding="utf-8")
    return {name.replace(".", "_") for name in re.findall(r'create_\w+\(\s*"([^"]+)"', source)}


def _check_metric_names(charts: list[dict]) -> None:
    """Không cho phép biểu đồ hỏi một chỉ số mà hệ thống không hề phát ra.

    Một panel trỏ sai tên thì không báo lỗi — nó chỉ hiện đường trống, và người
    xem tưởng hệ thống đang im ắng. Đây là kiểu hỏng im lặng nên phải chặn ở CI.
    Chỉ soát tiền tố fin07_ vì chỉ số của exporter bên thứ ba (node, cadvisor,
    postgres…) không do repo này khai báo.
    """
    declared = _declared_metric_names()
    suffixes = ("_bucket", "_sum", "_count", "_total")
    unknown: set[str] = set()
    for chart in charts:
        for target in chart.get("targets", []):
            for used in re.findall(r"\bfin07_[a-z0-9_]+", target.get("expr", "")):
                base = used
                for suffix in suffixes:
                    if base.endswith(suffix):
                        base = base[: -len(suffix)]
                        break
                if base not in declared and used not in declared:
                    unknown.add(used)
    if unknown:
        raise RuntimeError(f"Biểu đồ hỏi chỉ số không tồn tại trong src/observability/metrics.py: {sorted(unknown)}")


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
    # Hai bảng, hai câu hỏi khác nhau: "hệ thống chạy thế nào" và "tác tử AI
    # chạy thế nào". Gộp làm một thì người trực phải lướt qua chi phí token mới
    # thấy được độ trễ API — đó chính là lý do bảng cũ bị coi là "toàn metrics
    # agent".
    contracts = {
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
    dashboards = sorted((ROOT / "monitoring/grafana/dashboards").glob("*.json"))
    found = [path.name for path in dashboards]
    if found != sorted(contracts):
        raise RuntimeError(f"Phải có đúng các bảng {sorted(contracts)}, đang có {found}")

    charts: list[dict] = []
    rows: list[dict] = []
    for path in dashboards:
        document = json.loads(path.read_text(encoding="utf-8"))
        want_uid, expected_rows = contracts[path.name]
        if document.get("uid") != want_uid:
            raise RuntimeError(f"{path.name}: UID phải là {want_uid}, đang là {document.get('uid')}")
        panels = document.get("panels", [])
        d_rows = [panel for panel in panels if panel.get("type") == "row"]
        actual_rows = [str(row.get("title", "")).split("·")[-1].strip() for row in d_rows]
        if actual_rows != expected_rows:
            raise RuntimeError(f"{path.name}: phải giữ đúng {expected_rows}, đang có {actual_rows}")
        rows += d_rows
        charts += [panel for panel in panels if panel.get("type") != "row"]

    _check_metric_names(charts)

    panels = []
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
    # GRAFANA_BOARDS thay cho GRAFANA_OVERVIEW: tab Chỉ số phải cho chuyển giữa
    # bảng Hệ thống và bảng Tác tử. Nhúng cứng một bảng là quay lại đúng vấn đề
    # cũ — người trực không có đường nào xem độ trễ thật của hệ thống.
    for required in ('type Tab = "metrics" | "logs" | "traces"', "GRAFANA_BOARDS", "api.agentRuns"):
        if required not in panel:
            raise RuntimeError(f"Observability panel thiếu thành phần bắt buộc: {required}")
    print(f"đã kiểm {len(yaml_files)} file YAML, {len(rows)} nhóm chỉ số và {len(charts)} biểu đồ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
