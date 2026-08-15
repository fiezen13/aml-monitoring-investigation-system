from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opentelemetry import metrics


def _meter():
    return metrics.get_meter("fin07.observability", "1.0.0")


class Fin07Metrics:
    """Low-cardinality application instruments shared by API and worker."""

    def __init__(self) -> None:
        meter = _meter()
        self.http_requests = meter.create_counter("fin07.http.requests.total")
        self.http_duration = meter.create_histogram("fin07.http.request.duration.seconds")
        self.http_active = meter.create_up_down_counter("fin07.http.active_requests")
        self.worker_jobs = meter.create_counter("fin07.worker.jobs.total")
        self.worker_failures = meter.create_counter("fin07.worker.job.failures.total")
        self.worker_duration = meter.create_histogram("fin07.worker.job.duration.seconds")
        self.worker_queue_wait = meter.create_histogram("fin07.worker.queue.wait.seconds")
        self.worker_active = meter.create_up_down_counter("fin07.worker.active_jobs")
        self.worker_queue_depth = meter.create_gauge("fin07.worker.queue.depth")
        self.worker_available = meter.create_gauge("fin07.worker.available")
        self.worker_retries = meter.create_counter("fin07.worker.retries.total")
        self.worker_dead_jobs = meter.create_counter("fin07.worker.dead.jobs.total")
        self.worker_oldest_queue_age = meter.create_gauge("fin07.worker.queue.oldest.age.seconds")
        self.agent_runs = meter.create_counter("fin07.agent.runs.total")
        self.agent_failures = meter.create_counter("fin07.agent.failures.total")
        self.agent_duration = meter.create_histogram("fin07.agent.run.duration.seconds")
        self.agent_active = meter.create_up_down_counter("fin07.agent.active.runs")
        self.agent_iterations = meter.create_histogram("fin07.agent.iterations")
        self.tool_calls = meter.create_counter("fin07.agent.tool.calls.total")
        self.tool_duration = meter.create_histogram("fin07.agent.tool.duration.seconds")
        self.gemini_requests = meter.create_counter("fin07.gemini.requests.total")
        self.gemini_errors = meter.create_counter("fin07.gemini.errors.total")
        self.gemini_duration = meter.create_histogram("fin07.gemini.request.duration.seconds")
        self.gemini_input_tokens = meter.create_counter("fin07.gemini.input.tokens.total")
        self.gemini_output_tokens = meter.create_counter("fin07.gemini.output.tokens.total")
        self.gemini_retries = meter.create_counter("fin07.gemini.retries.total")
        self.investigations = meter.create_counter("fin07.investigations.total")
        self.investigation_duration = meter.create_histogram("fin07.investigation.duration.seconds")
        self.investigations_active = meter.create_up_down_counter("fin07.investigations.active")
        self.human_review = meter.create_counter("fin07.investigations.human.review.total")
        self.insufficient_evidence = meter.create_counter("fin07.investigations.insufficient.evidence.total")
        self.critic_validations = meter.create_counter("fin07.critic.validations.total")
        self.critic_issues = meter.create_counter("fin07.critic.issues.total")
        self.critic_duration = meter.create_histogram("fin07.critic.validation.duration.seconds")
        self.explanation_claim_count = meter.create_histogram("fin07.explanation.claim.count")
        self.explanation_fact_count = meter.create_histogram("fin07.explanation.fact.count")
        self.explanation_inference_count = meter.create_histogram("fin07.explanation.inference.count")
        self.explanation_evidence_refs_per_claim = meter.create_histogram("fin07.explanation.evidence.refs.per.claim")
        self.explanation_missing_count = meter.create_histogram("fin07.explanation.missing.information.count")
        self.explanation_schema_failures = meter.create_counter("fin07.explanation.schema.failures.total")
        self.supervisor_tool_calls = meter.create_histogram("fin07.supervisor.tool.calls.per.run")
        self.supervisor_open_questions = meter.create_histogram("fin07.supervisor.open.questions.per.run")
        self.supervisor_accounts_expanded = meter.create_histogram("fin07.supervisor.accounts.expanded.per.run")
        self.supervisor_limit_reached = meter.create_counter("fin07.supervisor.limit.reached.total")
        self.security_events = meter.create_counter("fin07.agent.security.events.total")


METRICS = Fin07Metrics()


def attrs(**values: Any) -> Mapping[str, str]:
    return {key: str(value) for key, value in values.items() if value is not None}
