# Redis evictions

## Meaning
Redis removed keys under memory pressure.
## Impact
Cache churn is possible; queue safety must be checked because Redis also carries jobs.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành**, inspect **Tải worker**, then switch to the **Traces** tab.

## How to verify
Compare memory/max memory, evictions, keys, clients, and FIN-07 queue depth in Prometheus, then inspect a worker trace.
## Useful queries
PromQL: `increase(redis_evicted_keys_total[10m])` and `redis_memory_used_bytes`.
## Likely causes
Memory ceiling, unexpected key growth, or eviction policy mismatch.
## Safe remediation
Preserve queue data; identify key class/TTL safely, increase capacity or correct retention/policy through configuration.
## Escalation
Platform owner; involve worker owner if queue keys or wait time are affected.
