from __future__ import annotations

import time
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

from opentelemetry import trace

from src.observability.context import bind_context
from src.observability.metrics import METRICS, attrs
from src.observability.telemetry import record_safe_exception, tracer


class AgentObservation(AbstractContextManager["AgentObservation"]):
    def __init__(self, agent: str, iteration: int) -> None:
        self.agent = agent
        self.iteration = iteration
        self.started = 0.0
        self.span_cm: Any = None
        self.context_cm: Any = None
        self.span: trace.Span | None = None

    def __enter__(self) -> AgentObservation:
        self.started = time.monotonic()
        self.context_cm = bind_context(agent=self.agent, iteration=self.iteration)
        self.context_cm.__enter__()
        self.span_cm = tracer().start_as_current_span(
            f"agent.{self.agent}",
            attributes={"aml.agent.name": self.agent, "aml.investigation.iteration": self.iteration},
        )
        self.span = self.span_cm.__enter__()
        METRICS.agent_active.add(1, attrs(agent=self.agent))
        return self

    def set_attribute(self, key: str, value: Any) -> None:
        if self.span is not None and value is not None:
            self.span.set_attribute(key, value)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        duration = time.monotonic() - self.started
        status = "success"
        if exc is not None:
            status = "timeout" if "timeout" in type(exc).__name__.lower() else "failure"
            METRICS.agent_failures.add(1, attrs(agent=self.agent, error_type=type(exc).__name__))
            if self.span is not None:
                record_safe_exception(self.span, exc)
                self.span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
        METRICS.agent_runs.add(1, attrs(agent=self.agent, status=status))
        METRICS.agent_duration.record(duration, attrs(agent=self.agent))
        METRICS.agent_active.add(-1, attrs(agent=self.agent))
        try:
            return bool(self.span_cm.__exit__(None, None, None))
        finally:
            self.context_cm.__exit__(None, None, None)


class ToolObservation(AbstractContextManager["ToolObservation"]):
    def __init__(self, agent: str, tool: str) -> None:
        self.agent = agent
        self.tool = tool
        self.started = 0.0
        self.status = "success"
        self.result_count = 0
        self.span_cm: Any = None
        self.context_cm: Any = None
        self.span: trace.Span | None = None

    def __enter__(self) -> ToolObservation:
        self.started = time.monotonic()
        self.context_cm = bind_context(agent=self.agent, tool=self.tool)
        self.context_cm.__enter__()
        self.span_cm = tracer().start_as_current_span(
            f"tool.{self.tool}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "aml.agent.name": self.agent,
                "aml.tool.name": self.tool,
            },
        )
        self.span = self.span_cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc is not None:
            self.status = "failure"
            if self.span is not None:
                self.span.set_attribute("error.type", type(exc).__name__)
                record_safe_exception(self.span, exc)
                self.span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
        dimensions = attrs(agent=self.agent, tool=self.tool, status=self.status)
        METRICS.tool_calls.add(1, dimensions)
        METRICS.tool_duration.record(time.monotonic() - self.started, attrs(agent=self.agent, tool=self.tool))
        if self.span is not None:
            self.span.set_attribute("aml.tool.status", self.status)
            self.span.set_attribute("aml.tool.result_count", self.result_count)
        try:
            return bool(self.span_cm.__exit__(None, None, None))
        finally:
            self.context_cm.__exit__(None, None, None)
