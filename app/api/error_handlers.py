"""Respuestas de error coherentes con request_id para soporte y logs."""

from __future__ import annotations

import logging
import traceback

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    rid = _request_id(request)
    body: dict = {"detail": exc.detail, "request_id": rid}
    hdrs = dict(getattr(exc, "headers", None) or {})
    hdrs["X-Request-ID"] = rid
    return JSONResponse(status_code=exc.status_code, content=body, headers=hdrs)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    rid = _request_id(request)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": rid},
        headers={"X-Request-ID": rid},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    logger.error(
        "Unhandled error request_id=%s path=%s\n%s",
        rid,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": rid,
        },
        headers={"X-Request-ID": rid},
    )
