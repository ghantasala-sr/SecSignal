"""OpenTelemetry tracing middleware stub.

Provides basic request tracing for the FastAPI app. Full OTel integration
with Snowflake spans is planned for Week 4.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Adds request ID and timing to each request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request_id to request state for downstream use
        request.state.request_id = request_id

        logger.info(
            "request_start",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        logger.info(
            "request_end",
            request_id=request_id,
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 1),
        )

        return response
