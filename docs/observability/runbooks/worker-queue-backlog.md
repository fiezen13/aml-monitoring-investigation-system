# Worker queue backlog

## Meaning
Queue depth/wait increased or worker heartbeat disappeared.
## Impact
Investigations remain queued and analyst-visible results are delayed.
## Grafana dashboard

Open **FIN-07 — Tổng quan vận hành**, inspect **Tải worker**, then select `fin07-worker` in **Nhật ký lỗi** or **Traces**.

## How to verify
Compare queue wait, active jobs, job duration, and failures, then open a slow/error trace to find the blocking child span.
## Useful queries
PromQL: `max(fin07_worker_queue_depth)` and `histogram_quantile(0.95,sum by(le)(rate(fin07_worker_queue_wait_seconds_bucket[5m])))`. LogQL: `{service_name="fin07-worker"} | level=~"ERROR|WARNING"`.
## Likely causes
Worker down, slow Gemini/agent/tool path, DB contention, or arrival-rate burst.
## Safe remediation
Restart an unhealthy worker after preserving logs; scale only if job idempotency/capacity is confirmed; do not delete queued jobs.
## Escalation
Worker owner, then AI/provider or dependency owner indicated by traces.
