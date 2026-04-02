from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import get_settings
from app.infrastructure.face_detection import MediaPipeFaceDetector

if TYPE_CHECKING:
    from app.infrastructure.hair_inpaint_generator import HairInpaintGenerator

logger = logging.getLogger(__name__)

_face_detector: MediaPipeFaceDetector | None = None
_generator = None


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
