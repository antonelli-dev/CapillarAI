"""API key validation: X-API-Key or Authorization: Bearer <key>."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _configured_keys() -> frozenset[str]:
    raw = get_settings().api_keys
    if not raw:
        return frozenset()
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _matches_any(provided: str, valid: frozenset[str]) -> bool:
    p = provided.encode("utf-8")
    for k in valid:
        if secrets.compare_digest(p, k.encode("utf-8")):
            return True
    return False


async def require_api_key(
    x_api_key: str | None = Security(_api_key_header),
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    valid = _configured_keys()
    if not valid:
        return
    token = x_api_key or _extract_bearer(authorization)
    if not token or not _matches_any(token, valid):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Use X-API-Key or Authorization: Bearer <key>.",
        )
