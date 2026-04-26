"""slowapi: per-client limits using API key hash or client IP."""

from __future__ import annotations

import hashlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    k = request.headers.get("X-API-Key") or ""
    if not k:
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            k = auth[7:].strip()
    if k:
        digest = hashlib.sha256(k.encode("utf-8")).hexdigest()[:32]
        return f"k:{digest}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_limit_key)
