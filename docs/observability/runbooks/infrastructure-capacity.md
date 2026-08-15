# Infrastructure capacity pressure

## Meaning

Host disk free space is below 15%, or memory utilization remains above 90%.

## Impact

Containers can be OOM-killed, writes can fail, and PostgreSQL, Loki, or Docker may become unavailable.

## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and correlate **Áp lực tài nguyên** with failure/latency on the same time axis.

## How to verify

Confirm the alert in Prometheus and inspect `node_filesystem_avail_bytes`, `node_memory_MemAvailable_bytes`, and cAdvisor container metrics.

## Useful queries

`100 * node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}`; `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)`.

## Likely causes

Unbounded Docker layers/logs, telemetry retention, bulk data jobs, memory leaks, or a host sized below current workload.

## Safe remediation

Identify the largest consumer first. Rotate or archive known disposable logs and artifacts under the approved retention policy; throttle batch work; scale the host before restarting stateful services.

## Escalation

Escalate immediately below 8% disk or when OOM kills/write failures begin; include top consumers and growth rate.
