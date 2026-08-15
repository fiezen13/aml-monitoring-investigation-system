# Agent loop limit

## Meaning
Investigations reached configured iteration or tool-call bounds. Threshold is provisional.
## Impact
Latency/tokens grow and investigations safely stop as insufficient evidence/human review.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành**, inspect **Nguyên nhân failure AI**, then use the separate **Nhật ký lỗi** and **Traces** tabs.

## How to verify
Filter the agent/tool, then inspect a trace for repeated tool fingerprints, Critic issue type, retries, and per-agent duration.
## Useful queries
PromQL: `sum by(limit)(increase(fin07_supervisor_limit_reached_total[15m]))`. LogQL: `{service_name="fin07-worker"} |= "limit"`.
## Likely causes
Repeated identical requests, unavailable evidence, failing tools, Critic feedback not resolved, or prompt regression.
## Safe remediation
Repair evidence/tool behavior; tune limits only after replaying mocked investigations and reviewing token/latency impact.
## Escalation
AI platform and AML investigation workflow owners.
