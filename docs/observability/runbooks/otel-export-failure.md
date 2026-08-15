# OpenTelemetry export failure

## Meaning
The Collector cannot export one or more telemetry signals or is dropping data.
## Impact
Incident diagnosis becomes incomplete even if AML processing still works.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and compare metric gaps with the separate **Nhật ký lỗi** and **Traces** views.

## How to verify
Check Prometheus target `otel-collector`, Collector logs, exporter failure, queue, refused, and dropped telemetry metrics; check Loki/Jaeger health.
## Useful queries
PromQL: `{__name__=~"otelcol_exporter_send_failed_.*"}`. LogQL: `{service_name="fin07-otel-collector"} | level="ERROR"`.
## Likely causes
Backend down, invalid OTLP payload/config, queue saturation, network, or Collector memory pressure.
## Safe remediation
Restore the failing backend or last known Collector config; do not make the application depend on Grafana/Jaeger health.
## Escalation
Observability owner; escalate storage/network faults to platform owner.
