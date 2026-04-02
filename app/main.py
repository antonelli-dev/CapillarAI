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
    from app.deps import get_generator

    get_generator()
    logging.getLogger(__name__).info("Modelo listo | perfil=%s", settings.profile)
    yield


app = FastAPI(title="Hair AI", lifespan=lifespan)

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
    return {"status": "ok", "service": "hair-ai"}


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(upload_router)
app.include_router(generate_router)
