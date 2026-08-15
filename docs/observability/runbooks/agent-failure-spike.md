# Agent failure spike

## Meaning
Operational failures increased for one of the three agents. Threshold is provisional.
## Impact
Investigations fail or stop for human review.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and correlate **Failure theo tầng** with AI failure causes, then inspect **Traces**.

## How to verify
Open an error trace, identify the failing agent span, then drill into Gemini/tool/DB children and its correlated logs.
## Useful queries
PromQL: `sum by(agent,error_type)(rate(fin07_agent_failures_total[10m]))`.
## Likely causes
Gemini failure, schema validation, tool/DB error, deployment regression, or limit exhaustion.
## Safe remediation
Address the failing child dependency; use mock-based rollback validation; do not bypass Critic or safety bounds.
## Escalation
Owning AI engineer plus dependency owner shown by the trace.
