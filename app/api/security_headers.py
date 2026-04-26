"""Cabeceras HTTP de endurecimiento (complementan TLS y proxy; no los sustituyen)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


def _request_is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    return forwarded == "https"


def apply_security_headers(request: Request, response: Response) -> None:
    """Añade cabeceras de seguridad; usa setdefault para no pisar valores explícitos de rutas."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # Desactiva el filtro XSS legacy del navegador (comportamiento recomendado actual).
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault(
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=(), interest-cohort=()",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    # No establecer CORP por defecto: same-origin rompería clientes en otro dominio aunque CORS permita el origen.

    settings = get_settings()
    if (
        _request_is_https(request)
        and settings.secure_hsts_max_age is not None
        and settings.secure_hsts_max_age > 0
    ):
        parts = [f"max-age={settings.secure_hsts_max_age}"]
        if settings.secure_hsts_include_subdomains:
            parts.append("includeSubDomains")
        if settings.secure_hsts_preload:
            parts.append("preload")
        response.headers.setdefault(
            "Strict-Transport-Security",
            "; ".join(parts),
        )

    path = request.url.path
    if path.startswith("/v1/") or path in ("/docs", "/redoc", "/openapi.json"):
        response.headers.setdefault("Cache-Control", "no-store, private")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        apply_security_headers(request, response)
        return response
