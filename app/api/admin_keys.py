"""
Gestión de API keys en SQLite vía ADMIN_SECRET (sin tocar inferencia).

Requiere API_KEYS_DB. Las claves de solo-entorno (API_KEYS) no aparecen en listado.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from app.api.auth import extract_bearer_token
from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.infrastructure.api_key_repository import get_api_key_repository

router = APIRouter(prefix="/admin", tags=["admin"])

# Entropía comparable a muchas APIs (32 bytes URL-safe ≈ 256 bits codificados en base64url).
_GENERATED_KEY_BYTES = 32
_PLAIN_KEY_MAX = 512


def require_admin(
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    s = get_settings()
    if not s.admin_secret:
        raise HTTPException(status_code=404, detail="Admin API not configured")
    token = x_admin_secret or extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=403, detail="Missing admin secret")
    if not secrets.compare_digest(
        token.encode("utf-8"),
        s.admin_secret.encode("utf-8"),
    ):
        raise HTTPException(status_code=403, detail="Invalid admin secret")


_settings = get_settings()


class CreateKeyBody(BaseModel):
    """Si `generate` es true, se ignora `plain_key` y el servidor genera una clave segura."""

    generate: bool = Field(
        False,
        description="Si true, se crea una clave aleatoria (se devuelve en texto una sola vez).",
    )
    plain_key: str | None = Field(
        None,
        max_length=_PLAIN_KEY_MAX,
        description="Clave en texto (solo si generate=false). Mínimo 8 caracteres.",
    )
    label: str = Field("", max_length=128)

    @model_validator(mode="after")
    def plain_or_generate(self) -> CreateKeyBody:
        if self.generate:
            self.plain_key = None
            return self
        pk = (self.plain_key or "").strip()
        if len(pk) < 8:
            raise ValueError("plain_key requerida (mínimo 8 caracteres) o usa generate=true")
        self.plain_key = pk
        return self


@router.get(
    "/keys",
    summary="Listar claves (SQLite)",
)
@limiter.limit(_settings.rate_limit_upload)
def list_api_keys(
    request: Request,
    active_only: bool = Query(
        True,
        description="Si false, incluye revocadas (active=0).",
    ),
    _auth: None = Depends(require_admin),
):
    _ = request.client
    repo = get_api_key_repository()
    return {"keys": repo.list_db_keys(active_only=active_only)}


@router.post(
    "/keys",
    summary="Crear clave para cliente",
)
@limiter.limit(_settings.rate_limit_upload)
def create_api_key(
    request: Request,
    body: CreateKeyBody,
    _auth: None = Depends(require_admin),
):
    _ = request.client
    repo = get_api_key_repository()
    if not get_settings().api_keys_db:
        raise HTTPException(
            status_code=400,
            detail="Configure API_KEYS_DB to store keys in SQLite",
        )
    if body.generate:
        plain = secrets.token_urlsafe(_GENERATED_KEY_BYTES)
    else:
        plain = body.plain_key or ""
        adm = get_settings().admin_secret
        if adm and secrets.compare_digest(
            plain.encode("utf-8"),
            adm.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=400,
                detail="plain_key must not equal the admin secret",
            )
    h = repo.add_key(plain, label=body.label.strip())
    out: dict = {
        "ok": True,
        "key_hash_prefix": h[:16],
        "message": "Guarda la clave en un gestor seguro; no se puede recuperar del servidor.",
    }
    if body.generate:
        out["api_key"] = plain
        out["hint"] = "Esta es la única vez que verás la clave en claro."
    return out


@router.delete(
    "/keys/{key_id}",
    summary="Revocar clave por id (rowid SQLite)",
)
@limiter.limit(_settings.rate_limit_upload)
def revoke_api_key(
    request: Request,
    key_id: int,
    _auth: None = Depends(require_admin),
):
    _ = request.client
    repo = get_api_key_repository()
    if not repo.revoke_by_id(key_id):
        raise HTTPException(status_code=404, detail="Key id not found")
    return {"ok": True, "revoked_id": key_id}
