import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.generate import router as generate_router
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

    from app.deps import get_face_detector, get_generator
    get_face_detector()
    log.info("MediaPipe listo")
    get_generator()
    log.info("Modelo listo | perfil=%s", settings.profile)

    yield


app = FastAPI(title="CapillarAI", version="1.0.0", lifespan=lifespan)

_settings = get_settings()
if _settings.cors_origins:
    _origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
    if _origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


@app.get("/")
def root():
    return {"status": "ok", "service": "CapillarAI"}


@app.get("/health")
def health():
    from app.deps import queue_depth, MAX_PENDING
    depth = queue_depth()
    return {
        "status": "healthy" if depth < MAX_PENDING else "busy",
        "queue": {"pending": depth, "max": MAX_PENDING},
    }


app.include_router(upload_router)
app.include_router(generate_router)
