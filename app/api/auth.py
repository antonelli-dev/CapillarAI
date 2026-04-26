"""API key validation: X-API-Key or Authorization: Bearer <key>."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.infrastructure.api_key_repository import get_api_key_repository

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


async def require_api_key(
    x_api_key: str | None = Security(_api_key_header),
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    repo = get_api_key_repository()
    if not repo.has_auth_configured():
        return
    token = x_api_key or extract_bearer_token(authorization)
    if not repo.is_valid(token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Use X-API-Key or Authorization: Bearer <key>.",
        )
