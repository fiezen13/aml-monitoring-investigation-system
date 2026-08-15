# Gemini rate limit

## Meaning
Gemini calls are receiving bounded `rate_limit` errors. Alert threshold is provisional.
## Impact
Agents retry, investigations slow, and may end in safe human review.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and inspect **Nguyên nhân failure AI** plus p95 latency.

## How to verify
Filter by agent, select `rate_limit`, then inspect a failed trace without prompt content.
## Useful queries
PromQL: `sum by(agent)(rate(fin07_gemini_errors_total{error_type="rate_limit"}[10m]))`.
## Likely causes
Quota exhaustion, burst concurrency, regional/provider constraint, or retry amplification.
## Safe remediation
Reduce approved concurrency, honor backoff, confirm quota in the provider console; never rotate/expose keys in logs.
## Escalation
AI platform owner and provider/quota administrator.
