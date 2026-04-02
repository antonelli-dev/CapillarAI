"""
Automatic studio-style background (flat neutral gray) when segmentation is confident.

Uses rembg (U²-Net). First call may download model weights (~176MB).
If the alpha mask looks unreliable, returns the original BGR image unchanged.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_BG_RGB = (245, 245, 245)

# rembg fails on bald-head edges and a flat gray studio bg before SD can cause muddy tints.
# Skip when alopecia is very high or the inpaint mask would cover too much of the frame.
SEVERITY_SKIP_REMBG = 0.82
MASK_FRAC_SKIP_REMBG = 0.22

try:
    from rembg import remove as _rembg_remove
except ImportError:  # pragma: no cover
    _rembg_remove = None


def _mask_confidence_ok(alpha: np.ndarray) -> bool:
    h, w = alpha.shape
    if h * w <= 0:
        return False

    subject_frac = np.mean(alpha > 128)
    if subject_frac < 0.07 or subject_frac > 0.94:
        logger.debug("Segmentación: fracción sujeto=%.2f (rechazo)", subject_frac)
        return False

    cy, cx = h // 2, w // 2
    rh, rw = max(8, h // 5), max(8, w // 5)
    y0, y1 = max(0, cy - rh), min(h, cy + rh)
    x0, x1 = max(0, cx - rw), min(w, cx + rw)
    center = alpha[y0:y1, x0:x1]
    if center.size == 0 or float(np.mean(center)) < 70:
        logger.debug("Segmentación: centro vacío (rechazo)")
        return False

    if np.mean(alpha < 15) < 0.015 and subject_frac > 0.93:
        logger.debug("Segmentación: poca separación fondo/sujeto (rechazo)")
        return False

    return True


def should_replace_background(severity: float, mask_fraction: float) -> bool:
    """
    When False, caller should inpaint on the original photo (no synthetic gray behind the head).
    """
    if severity > SEVERITY_SKIP_REMBG:
        logger.info(
            "Fondo: rembg omitido (severidad %.2f > %.2f)",
            severity,
            SEVERITY_SKIP_REMBG,
        )
        return False
    if mask_fraction > MASK_FRAC_SKIP_REMBG:
        logger.info(
            "Fondo: rembg omitido (máscara grande %.1f%% > %.1f%%)",
            100.0 * mask_fraction,
            100.0 * MASK_FRAC_SKIP_REMBG,
        )
        return False
    return True


def maybe_replace_background_flat(
    image_bgr: np.ndarray,
    severity: float,
    mask_fraction: float,
) -> tuple[np.ndarray, bool]:
    """
    Runs studio flat background only when severity and mask size are in a safe range.
    Returns (image_bgr, True) if rembg replaced the background, else (original, False).
    """
    if not should_replace_background(severity, mask_fraction):
        return image_bgr, False
    return try_replace_background_flat(image_bgr)


def try_replace_background_flat(image_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    """
    Returns (image_bgr, True) if background was replaced, else (original, False).
    """
    if _rembg_remove is None:
        logger.warning("rembg no instalado; ejecuta: pip install rembg")
        return image_bgr, False

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    try:
        rgba = _rembg_remove(pil)
    except Exception as e:
        logger.warning("rembg falló (%s); imagen original", e)
        return image_bgr, False

    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")

    alpha = np.asarray(rgba.split()[3])
    if not _mask_confidence_ok(alpha):
        logger.info(
            "Fondo: segmentación poco fiable — se usa imagen original (sin sustituir fondo)"
        )
        return image_bgr, False

    bg = Image.new("RGB", rgba.size, DEFAULT_BG_RGB)
    bg.paste(rgba, mask=rgba.split()[3])
    out = cv2.cvtColor(np.asarray(bg), cv2.COLOR_RGB2BGR)
    logger.info("Fondo: reemplazado por gris estudio (segmentación OK)")
    return out, True
