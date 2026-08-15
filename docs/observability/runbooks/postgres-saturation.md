# PostgreSQL saturation

## Meaning
PostgreSQL is unreachable or connection utilization is high.
## Impact
API, worker, tools, and persistence can fail together.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and correlate **Áp lực tài nguyên** with failures, then use **Traces**.

## How to verify
Inspect the PostgreSQL exporter metrics, then use a correlated trace to identify slow or blocked DB spans.
## Useful queries
PromQL: `sum(pg_stat_activity_count)/max(pg_settings_max_connections)` and `sum by(mode)(pg_locks_count)`.
## Likely causes
Connection leak, slow/blocked transactions, insufficient pool/DB capacity, or network failure.
## Safe remediation
Identify blocking sessions and application source before cancellation; roll back leaks; adjust limits only with capacity analysis.
## Escalation
Database owner immediately for sustained >85% utilization or lock pile-up.
