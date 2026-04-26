from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.config import get_settings
from app.infrastructure.face_detection import MediaPipeFaceDetector

if TYPE_CHECKING:
    from app.infrastructure.hair_inpaint_generator import HairInpaintGenerator

logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────

_face_detector: MediaPipeFaceDetector | None = None
_generator: HairInpaintGenerator | None = None

# ── GPU inference queue ───────────────────────────────────────────────────────
# One thread, one semaphore: GPU can only run one inference at a time.
# Requests queue up in async-land without blocking the event loop.

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gpu-infer")
_semaphore = asyncio.Semaphore(1)

# Requests currently waiting OR running.
_pending: int = 0

# Hard cap: if this many requests are already queued, reject immediately (503).
# With ~15s per inference, 8 queued = max ~2 min wait. Adjust per SLA.
MAX_PENDING: int = 8

# Per-request wall-clock timeout (seconds). Covers queue wait + inference.
INFERENCE_TIMEOUT: float = 180.0


def get_face_detector() -> MediaPipeFaceDetector:
    global _face_detector
    if _face_detector is None:
        _face_detector = MediaPipeFaceDetector()
    return _face_detector


def get_generator() -> HairInpaintGenerator:
    global _generator
    if _generator is None:
        from app.infrastructure.hair_inpaint_generator import HairInpaintGenerator
        logger.info("Inicializando HairInpaintGenerator...")
        _generator = HairInpaintGenerator(get_settings())
    return _generator


def get_validator():
    """ValidatePortraitUseCase backed by the shared face detector."""
    from app.application.validate_portrait import ValidatePortraitUseCase
    return ValidatePortraitUseCase(get_face_detector())


def get_generate_hair_use_case():
    """Application layer: delegates to ImageGeneratorPort (HairInpaintGenerator)."""
    from app.application.generate_hair import GenerateHairUseCase
    return GenerateHairUseCase(get_generator())


def queue_depth() -> int:
    """Number of inference requests currently waiting or running."""
    return _pending


async def run_inference(image_bgr, face_landmarks, seed: int | None = None):
    """
    Run hair inpainting on the GPU worker thread.

    - Rejects with 503 when the queue is full (backpressure).
    - Serialises access to the pipeline via asyncio.Semaphore(1).
    - Runs the blocking inference in a ThreadPoolExecutor so the event loop
      stays responsive for health-checks, uploads, etc.
    - Times out with 504 if inference + queue wait exceeds INFERENCE_TIMEOUT.
    """
    global _pending

    if _pending >= MAX_PENDING:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Servidor ocupado ({_pending} solicitudes en cola). "
                "Inténtalo en unos segundos."
            ),
        )

    _pending += 1
    try:
        async with _semaphore:
            loop = asyncio.get_event_loop()
            use_case = get_generate_hair_use_case()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        partial(
                            use_case.execute,
                            image_bgr,
                            face_landmarks,
                            seed=seed,
                        ),
                    ),
                    timeout=INFERENCE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=504,
                    detail="La generación tardó demasiado. Inténtalo de nuevo.",
                )
            return result
    finally:
        _pending -= 1


# ── New SaaS Infrastructure ─────────────────────────────────────────────────

# Job Repository (SQLite)
_job_repository = None

def get_job_repository():
    """SQLite implementation of JobRepositoryPort."""
    global _job_repository
    if _job_repository is None:
        from app.infrastructure.sqlite_job_repository import SQLiteJobRepository
        _job_repository = SQLiteJobRepository(db_path="jobs.db")
    return _job_repository


# Storage (Local filesystem - replace with S3/MinIO for production)
_storage = None

def get_storage():
    """StoragePort implementation. Use LocalStorage for dev, S3Storage for prod."""
    global _storage
    if _storage is None:
        # For MVP: local filesystem storage
        # For production: implement S3Storage or MinIOStorage
        from app.infrastructure.local_storage import LocalStorage
        _storage = LocalStorage(base_path="./storage")
    return _storage


# Donor Analyzer (CPU-only)
_donor_analyzer = None

def get_donor_analyzer():
    """OpenCV-based donor area analyzer (no GPU required)."""
    global _donor_analyzer
    if _donor_analyzer is None:
        from app.infrastructure.opencv_donor_analyzer import OpenCVDonorAnalyzer
        _donor_analyzer = OpenCVDonorAnalyzer()
    return _donor_analyzer


# PDF Generator
_pdf_generator = None

def get_pdf_generator():
    """ReportLab PDF generator for medical reports."""
    global _pdf_generator
    if _pdf_generator is None:
        from app.infrastructure.pdf_reportlab_generator import ReportLabPDFGenerator
        _pdf_generator = ReportLabPDFGenerator()
    return _pdf_generator


# Preset Repository (SQLite, shared with jobs DB)
_preset_repository = None

def get_preset_repository():
    """SQLite implementation of PresetRepositoryPort."""
    global _preset_repository
    if _preset_repository is None:
        from app.infrastructure.sqlite_preset_repository import SQLitePresetRepository
        _preset_repository = SQLitePresetRepository(db_path="jobs.db")
    return _preset_repository


# Webhook Dispatcher
_webhook_dispatcher = None

def get_webhook_dispatcher():
    """HTTP webhook dispatcher for async notifications."""
    global _webhook_dispatcher
    if _webhook_dispatcher is None:
        from app.infrastructure.http_webhook_dispatcher import HTTPWebhookDispatcher
        _webhook_dispatcher = HTTPWebhookDispatcher()
    return _webhook_dispatcher


# ── SaaS Use Cases ────────────────────────────────────────────────────────────

def get_create_job_use_case():
    """CreateSimulationJobUseCase for async job creation."""
    from app.application.create_simulation_job import CreateSimulationJobUseCase
    return CreateSimulationJobUseCase(
        job_repository=get_job_repository(),
        storage=get_storage(),
    )


def get_process_job_use_case():
    """ProcessSimulationJobUseCase for job execution."""
    from app.application.process_simulation_job import ProcessSimulationJobUseCase
    return ProcessSimulationJobUseCase(
        job_repository=get_job_repository(),
        storage=get_storage(),
        image_generator=get_generator(),
        donor_analyzer=get_donor_analyzer(),
        pdf_generator=get_pdf_generator(),
        webhook_dispatcher=get_webhook_dispatcher(),
    )


def get_analyze_donor_use_case():
    """AnalyzeDonorAreaUseCase for donor viability analysis."""
    from app.application.analyze_donor_area import AnalyzeDonorAreaUseCase
    return AnalyzeDonorAreaUseCase(
        donor_analyzer=get_donor_analyzer(),
        storage=get_storage(),
    )


def get_manage_presets_use_case():
    """ManagePresetsUseCase for hairline preset CRUD."""
    from app.application.manage_presets import ManagePresetsUseCase
    return ManagePresetsUseCase(
        preset_repository=get_preset_repository(),
    )


def get_gdpr_management_use_case():
    """GDPRDataManagementUseCase for data export/deletion."""
    from app.application.gdpr_data_management import GDPRDataManagementUseCase
    return GDPRDataManagementUseCase(
        job_repository=get_job_repository(),
        storage=get_storage(),
    )
