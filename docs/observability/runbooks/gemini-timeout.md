# Gemini timeout

## Meaning
Gemini calls exceeded configured timeout. Alert threshold is provisional.
## Impact
Agent latency/retries rise and investigations may require human review.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and correlate **Nguyên nhân failure AI** with p95 latency, then use **Traces**.

## How to verify
Compare Gemini p95/p99, retry rate, agent latency, and network/host health; inspect slow Jaeger spans.
## Useful queries
PromQL: `sum by(agent,model)(rate(fin07_gemini_errors_total{error_type="timeout"}[10m]))`.
## Likely causes
Provider latency, network degradation, oversized structured context, or resource contention.
## Safe remediation
Reduce bounded context only through product review; validate connectivity; change timeout/retry budgets only with latency evidence.
## Escalation
AI platform owner; provider support for sustained external degradation.
