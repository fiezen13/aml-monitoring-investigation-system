from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.observability.context import bind_context
from src.observability.metrics import METRICS, attrs


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request correlation plus bounded RED metrics; never reads the body."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", "")[:128] or str(uuid.uuid4())
        started = time.monotonic()
        status_code = 500
        METRICS.http_active.add(1, attrs(method=request.method))
        with bind_context(request_id=request_id):
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("http.request.id", request_id)
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers["x-request-id"] = request_id
                return response
            finally:
                route = request.scope.get("route")
                route_path = getattr(route, "path", "unmatched")
                dimensions = attrs(
                    method=request.method,
                    route=route_path,
                    status_class=f"{status_code // 100}xx",
                )
                METRICS.http_requests.add(1, dimensions)
                METRICS.http_duration.record(time.monotonic() - started, dimensions)
                METRICS.http_active.add(-1, attrs(method=request.method))
