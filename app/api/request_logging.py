"""Structured request logs (JSON) for latency and status — no image bodies."""

from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("capillarai.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = str(uuid.uuid4())[:8]
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                json.dumps(
                    {
                        "request_id": rid,
                        "method": request.method,
                        "path": request.url.path,
                        "status": "error",
                        "duration_ms": round(duration_ms, 2),
                    }
                )
            )
            raise
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            json.dumps(
                {
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
        )
        response.headers["X-Request-ID"] = rid
        return response
