# High API latency

## Meaning
FastAPI p95 exceeded the provisional engineering threshold.
## Impact
Analyst workflows are slow; queued investigations may begin late.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and inspect p95 latency, then switch to **Traces** with `fin07-backend`.

## How to verify
Click an exemplar or Jaeger trace and separate DB, Redis, and request time in the span waterfall.
## Useful queries
PromQL: `histogram_quantile(0.95, sum by (route,le) (rate(fin07_http_request_duration_seconds_bucket[5m])))`. Search Jaeger by service and slow duration.
## Likely causes
DB saturation, Redis latency, host pressure, synchronous route regression, or traffic change.
## Safe remediation
Protect capacity, roll back a regression, or tune only after a trace identifies the bottleneck.
## Escalation
API owner; route to DB/platform owner with trace evidence.
