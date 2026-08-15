from __future__ import annotations

import atexit
import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, ParentBased, TraceIdRatioBased

from src.config import Settings
from src.observability.logging import CorrelationFilter, JsonFormatter, configure_console_logging

_INITIALIZED = False
_LOGGER_PROVIDER: LoggerProvider | None = None
_TRACER_PROVIDER: TracerProvider | None = None
_METER_PROVIDER: MeterProvider | None = None
_SHUTDOWN = False


def _resource(settings: Settings) -> Resource:
    attributes: dict[str, Any] = {
        "service.name": settings.otel_service_name,
        "service.version": settings.otel_service_version,
        "service.instance.id": settings.otel_service_instance_id or os.getenv("HOSTNAME") or socket.gethostname(),
        "deployment.environment.name": settings.app_env,
    }
    if settings.git_commit_sha:
        attributes["vcs.ref.head.revision"] = settings.git_commit_sha
    if settings.build_version:
        attributes["build.version"] = settings.build_version
    for item in settings.otel_resource_attributes.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            if key.strip() and value.strip():
                attributes[key.strip()] = value.strip()
    return Resource.create(attributes)


def _sampler(settings: Settings):
    if settings.otel_traces_sampler == "always_on":
        return ALWAYS_ON
    if settings.otel_traces_sampler == "always_off":
        return ALWAYS_OFF
    return ParentBased(TraceIdRatioBased(settings.otel_traces_sampler_arg))


def _http_endpoint(base: str, signal: str) -> str:
    return f"{base.rstrip('/')}/v1/{signal}"


def initialize_observability(settings: Settings) -> None:
    global _INITIALIZED, _LOGGER_PROVIDER, _TRACER_PROVIDER, _METER_PROVIDER
    if _INITIALIZED:
        return

    configure_console_logging(
        level=settings.log_level,
        service=settings.otel_service_name,
        environment=settings.app_env,
        json_logs=settings.log_format == "json",
    )
    resource = _resource(settings)
    readers: list[Any] = [PrometheusMetricReader()]

    if settings.otel_enabled:
        if settings.otel_exporter_otlp_protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            endpoint = settings.otel_exporter_otlp_endpoint
            insecure = urlparse(endpoint).scheme == "http"
            span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
            metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
            log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=insecure)
        else:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            base = settings.otel_exporter_otlp_endpoint
            span_exporter = OTLPSpanExporter(endpoint=_http_endpoint(base, "traces"))
            metric_exporter = OTLPMetricExporter(endpoint=_http_endpoint(base, "metrics"))
            log_exporter = OTLPLogExporter(endpoint=_http_endpoint(base, "logs"))

        _TRACER_PROVIDER = TracerProvider(
            resource=resource,
            sampler=_sampler(settings),
            shutdown_on_exit=False,
        )
        _TRACER_PROVIDER.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(_TRACER_PROVIDER)

        readers.append(
            PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=settings.otel_metric_export_interval_ms,
            )
        )

        _LOGGER_PROVIDER = LoggerProvider(resource=resource, shutdown_on_exit=False)
        _LOGGER_PROVIDER.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(_LOGGER_PROVIDER)
        otel_handler = LoggingHandler(level=settings.log_level, logger_provider=_LOGGER_PROVIDER)
        otel_handler.addFilter(CorrelationFilter())
        otel_handler.setFormatter(JsonFormatter(service=settings.otel_service_name, environment=settings.app_env))
        logging.getLogger().addHandler(otel_handler)

    _METER_PROVIDER = MeterProvider(
        resource=resource,
        metric_readers=readers,
        shutdown_on_exit=False,
    )
    metrics.set_meter_provider(_METER_PROVIDER)

    RedisInstrumentor().instrument()
    from src.db.session import get_engine

    SQLAlchemyInstrumentor().instrument(engine=get_engine(), enable_commenter=False)
    _INITIALIZED = True
    atexit.register(shutdown_observability)


def instrument_fastapi(app: Any) -> None:
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics",
        exclude_spans=["receive", "send"],
    )


def shutdown_observability() -> None:
    global _SHUTDOWN
    if _SHUTDOWN:
        return
    _SHUTDOWN = True
    if _LOGGER_PROVIDER is not None:
        _LOGGER_PROVIDER.shutdown()
    if _TRACER_PROVIDER is not None:
        _TRACER_PROVIDER.shutdown()
    if _METER_PROVIDER is not None:
        _METER_PROVIDER.shutdown()


def tracer():
    return trace.get_tracer("fin07", "1.0.0")


def record_safe_exception(span: trace.Span, exc: BaseException) -> None:
    """Record only a bounded error class, never exception text or payloads."""
    span.add_event(
        "exception",
        attributes={
            "exception.type": type(exc).__name__,
            "exception.escaped": False,
        },
    )
