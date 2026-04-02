from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
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


async def run_inference(image_bgr, face_landmarks):
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
                        use_case.execute,
                        image_bgr,
                        face_landmarks,
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
