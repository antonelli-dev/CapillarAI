import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.admin_keys import router as admin_keys_router
from app.api.auth import require_api_key
# Import donor analysis router (multi-zone support added 2026-04-26 - updated 18:05)
from app.api.donor_analysis import router as donor_analysis_router
from app.api.error_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.gdpr import router as gdpr_router
from app.api.generate import router as generate_router
from app.api.jobs import router as jobs_router
from app.api.openapi_info import API_DESCRIPTION, API_TITLE, API_VERSION, TAGS_METADATA
from app.api.presets import router as presets_router
from app.api.rate_limit_ext import limiter
from app.api.request_logging import RequestLoggingMiddleware
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.share_links import router as share_router
from app.api.upload import router as upload_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger(__name__)

    from app.infrastructure.api_key_repository import get_api_key_repository

    get_api_key_repository()

    from app.deps import get_face_detector, get_generator
    get_face_detector()
    log.info("MediaPipe listo")
    get_generator()
    log.info("Modelo listo | perfil=%s", settings.profile)

    if not get_api_key_repository().has_auth_configured():
        log.warning(
            "Sin API keys (API_KEYS / API_KEYS_DB): rutas protegidas abiertas — solo desarrollo"
        )

    if settings.environment == "production" and not settings.cors_origins.strip():
        log.warning(
            "CORS_ORIGINS vacío en production: los navegadores no podrán llamar la API cross-origin"
        )

    if settings.admin_secret:
        log.info("Admin API habilitada: POST/GET/DELETE /v1/admin/keys (X-Admin-Secret)")
        if len(settings.admin_secret) < 16:
            log.warning(
                "ADMIN_SECRET es corto (<16 caracteres); usa un valor aleatorio largo en producción"
            )

    yield


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_settings = get_settings()
if _settings.cors_origins.strip():
    _origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
    if _origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


@app.get("/", tags=["meta"])
def root():
    return {"status": "ok", "service": "CapillarAI", "api": "/v1"}


@app.get("/health", tags=["meta"])
def health():
    from app.deps import MAX_PENDING, queue_depth

    depth = queue_depth()
    return {
        "status": "healthy" if depth < MAX_PENDING else "busy",
        "queue": {"pending": depth, "max": MAX_PENDING},
    }


app.include_router(
    upload_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    generate_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)

# ── SaaS Features ───────────────────────────────────────────────────────────

# Async job processing
app.include_router(
    jobs_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)

# Donor area viability analysis (CPU-only, fast)
app.include_router(
    donor_analysis_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)

# Hairline presets per clinic
app.include_router(
    presets_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)

# Share links for patient results
app.include_router(
    share_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],  # Creation requires auth
)

# GDPR compliance endpoints
app.include_router(
    gdpr_router,
    prefix="/v1",
    dependencies=[Depends(require_api_key)],
)

# Public share link access (no auth required)
app.include_router(
    share_router,
    prefix="/p",
)

if get_settings().admin_secret:
    app.include_router(admin_keys_router, prefix="/v1")

Instrumentator().instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
)
