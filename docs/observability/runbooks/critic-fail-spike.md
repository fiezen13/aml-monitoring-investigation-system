# Critic FAIL spike

## Meaning
Evidence Critic rejects more explanations than the provisional baseline.
## Impact
More Supervisor loops, tool calls, latency, and human-review outcomes; this may also reflect correct safety detection.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành** and inspect **Nguyên nhân failure AI**.

## How to verify
Identify the Critic issue type, then filter one investigation in **Nhật ký lỗi** and open its trace.
## Useful queries
PromQL: `sum by(issue_type)(rate(fin07_critic_issues_total[30m]))`. LogQL: `{service_name="fin07-worker"} | agent="evidence_critic"`.
## Likely causes
Tool data gaps/failures, prompt/model behavior change, schema regression, or genuinely weak evidence.
## Safe remediation
Restore evidence/tool reliability or roll back a prompt/model change; never weaken validation solely to raise PASS rate.
## Escalation
AI safety/AML product owner; tool/data owner for concentrated missing evidence.
