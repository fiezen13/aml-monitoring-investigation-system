# High API error rate

## Meaning
FastAPI 5xx ratio exceeded the engineering threshold.
## Impact
React operations and investigation creation/read paths may fail.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành**, then select `fin07-backend` in **Nhật ký lỗi** or **Traces**.

## How to verify
Inspect the 5xx interval, then select a matching Jaeger error trace or click `TraceID` in a failure log.
## Useful queries
PromQL: `sum by (route) (rate(fin07_http_requests_total{status_class="5xx"}[5m]))`. LogQL: `{service_name="fin07-backend"} | level="ERROR"`.
## Likely causes
Database/Redis failure, unhandled code error, resource exhaustion, or bad deployment.
## Safe remediation
Check readiness and dependency dashboards; roll back the suspect release or reduce traffic only through the approved deployment procedure.
## Escalation
Backend owner, then database/platform owner if dependency spans dominate.
