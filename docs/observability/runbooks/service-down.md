# Scrape target down

## Meaning

Prometheus could not scrape a configured target for two minutes.

## Impact

The service may be unavailable, or observability for it may be blind.

## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành**, then select the affected service in **Nhật ký lỗi** or **Traces**.

## How to verify

Check `up{job="$job",instance="$instance"}` and Prometheus **Status → Targets**; test the target's health endpoint from the Prometheus network namespace.

## Useful queries

`up == 0`; `{service_name="$job"} |= "error"`; inspect recent traces for that service in Jaeger.

## Likely causes

Container/process stopped, bad scrape address, failed health dependency, network/DNS failure, or exporter crash.

## Safe remediation

Restore the dependency first, then restart only the affected stateless service if its logs show a clean shutdown/crash loop cause. Never restart PostgreSQL or Redis before checking persistence and clients.

## Escalation

Escalate to the owning service team immediately for a customer-facing target or after five minutes for telemetry-only exporters.
