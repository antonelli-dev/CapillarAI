import logging
from typing import NamedTuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# MediaPipe face mesh landmark indices that form the hairline arc (left ear → crown → right ear).
HAIRLINE_CHAIN = (
    234,
    127,
    162,
    21,
    54,
    103,
    67,
    109,
    10,
    338,
    297,
    332,
    284,
    251,
    389,
    356,
    454,
)


class LightingAnalysis(NamedTuple):
    severity: float
    ratio: float
    scalp_std: float
    scalp_brightness: float
    skin_brightness_median: float
    hard_lighting: bool


def _sample_gray_mean(image_bgr: np.ndarray, cx: int, cy: int, half: int = 12) -> float | None:
    h, w = image_bgr.shape[:2]
    x0, x1 = max(0, cx - half), min(w, cx + half)
    y0, y1 = max(0, cy - half), min(h, cy + half)
    if x1 <= x0 or y1 <= y0:
        return None
    patch = image_bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def analyze_scalp_lighting(image_bgr: np.ndarray, landmarks) -> LightingAnalysis:
    """
    Severity from scalp vs multi-zone skin (chin + cheeks median).
    hard_lighting: strong specular / uneven outdoor light (triggers preprocess + optional 2nd pass).
    """
    lm = landmarks.landmark
    h, w = image_bgr.shape[:2]

    brow_y = max(lm[107].y, lm[336].y) * h
    chin_y = lm[152].y * h
    face_height = max(1.0, chin_y - brow_y)

    scalp_top = max(0, int(brow_y - 0.55 * face_height))
    scalp_bot = max(scalp_top + 4, int(brow_y) - 4)

    face_left = lm[234].x * w
    face_right = lm[454].x * w
    cx = (face_left + face_right) / 2
    half_w = max(1.0, (face_right - face_left) * 0.25)
    roi_left = max(0, int(cx - half_w))
    roi_right = min(w - 1, int(cx + half_w))

    if roi_right <= roi_left or scalp_bot <= scalp_top:
        return LightingAnalysis(0.5, 1.0, 0.0, 128.0, 128.0, False)

    scalp_roi = image_bgr[scalp_top:scalp_bot, roi_left:roi_right]
    if scalp_roi.size == 0:
        return LightingAnalysis(0.5, 1.0, 0.0, 128.0, 128.0, False)

    scalp_gray = cv2.cvtColor(scalp_roi, cv2.COLOR_BGR2GRAY)
    scalp_brightness = float(scalp_gray.mean())
    scalp_std = float(scalp_gray.std())

    # Multi-zone skin: chin strip + left/right cheek (landmarks 205 / 425 are mid-cheek on Face Mesh).
    skin_samples: list[float] = []
    chin_top = max(0, int(chin_y - 0.10 * face_height))
    chin_bot = max(chin_top + 4, min(int(chin_y) + 4, h - 1))
    chin_patch = image_bgr[chin_top:chin_bot, roi_left:roi_right]
    if chin_patch.size > 0:
        skin_samples.append(float(cv2.cvtColor(chin_patch, cv2.COLOR_BGR2GRAY).mean()))

    for idx in (205, 425):
        cx_i = int(lm[idx].x * w)
        cy_i = int(lm[idx].y * h)
        m = _sample_gray_mean(image_bgr, cx_i, cy_i, half=14)
        if m is not None:
            skin_samples.append(m)

    if not skin_samples:
        return LightingAnalysis(0.5, 1.0, scalp_std, scalp_brightness, 128.0, False)

    skin_brightness_median = float(np.median(np.array(skin_samples)))

    if skin_brightness_median < 5:
        return LightingAnalysis(0.5, 1.0, scalp_std, scalp_brightness, skin_brightness_median, False)

    ratio = scalp_brightness / skin_brightness_median

    severity = (ratio - 0.55) / (0.92 - 0.55)
    severity = float(np.clip(severity, 0.0, 1.0))

    # Severe baldness with huge forehead mask: nudge severity up if ratio already high.
    if ratio > 1.35 and severity < 0.85:
        severity = min(1.0, severity + 0.05)

    # Hard lighting: specular scalp + uneven vs face, or very high local variance on scalp.
    hard_lighting = (
        ratio > 1.38
        or scalp_std > 30.0
        or (ratio > 1.22 and scalp_std > 22.0)
    )

    label = "severa" if severity > 0.65 else "moderada" if severity > 0.35 else "leve"
    logger.info(
        "Alopecia: %.2f (%s) | scalp=%.1f skin_med=%.1f ratio=%.2f std=%.1f | luz_dura=%s",
        severity,
        label,
        scalp_brightness,
        skin_brightness_median,
        ratio,
        scalp_std,
        hard_lighting,
    )
    return LightingAnalysis(
        severity=severity,
        ratio=ratio,
        scalp_std=scalp_std,
        scalp_brightness=scalp_brightness,
        skin_brightness_median=skin_brightness_median,
        hard_lighting=hard_lighting,
    )


def estimate_hair_loss_severity(image_bgr: np.ndarray, landmarks) -> float:
    """Backward-compatible: returns severity only."""
    return analyze_scalp_lighting(image_bgr, landmarks).severity


def _ensure_min_mask_fraction(
    mask: np.ndarray,
    w: int,
    h: int,
    min_frac: float = 0.10,
) -> np.ndarray:
    total = float(h * w)
    if total <= 0:
        return mask
    if np.sum(mask > 127) / total >= min_frac:
        return mask
    k = max(11, int(0.04 * min(w, h))) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    for _ in range(10):
        mask = cv2.dilate(mask, kernel, iterations=1)
        if np.sum(mask > 127) / total >= min_frac:
            break
    return mask


def build_hairline_band_mask(mask_gray: np.ndarray, bottom_frac: float = 0.24) -> np.ndarray:
    """
    Narrow band along the face-ward edge of the inpaint mask (lower edge of scalp region),
    for a second refinement pass on hairline blend.
    """
    ys, xs = np.where(mask_gray > 127)
    if len(ys) < 50:
        return np.zeros_like(mask_gray)

    y_min, y_max = int(ys.min()), int(ys.max())
    band_h = max(6, int((y_max - y_min) * bottom_frac))
    y_start = max(y_min, y_max - band_h)

    band = np.zeros_like(mask_gray)
    band[y_start : y_max + 1, :] = mask_gray[y_start : y_max + 1, :]
    band = np.where(band > 127, 255, 0).astype(np.uint8)

    if feather := (15 if band.shape[0] > 256 else 11):
        if feather % 2 == 0:
            feather += 1
        band = cv2.GaussianBlur(band, (feather, feather), 0)

    return band


def build_hair_mask_from_landmarks(
    width: int,
    height: int,
    landmarks,
    feather: int = 21,
    severity: float = 0.5,
) -> Image.Image:
    """
    Builds a binary inpaint mask covering the scalp above the target hairline.

    Parameters
    ----------
    severity:
        Hair-loss severity in [0, 1] from analyze_scalp_lighting().
        Controls hairline depth, crown height, lateral expansion and min coverage.
    """
    lm = landmarks.landmark
    h, w = height, width

    brow_y = max(lm[107].y, lm[336].y) * h
    chin_y = lm[152].y * h
    face_height = max(1.0, chin_y - brow_y)

    # Mask-only: ~1% face-height lower edge vs 0.24 base (more scalp in paint zone; no prompt change)
    hairline_pct = 0.23 - severity * 0.12
    y_bottom = max(8, int(brow_y - hairline_pct * face_height))

    forehead_y = lm[10].y * h
    crown_pct = 0.30 + severity * 0.20
    crown_y = max(0, int(forehead_y - crown_pct * face_height))

    pts = []
    for idx in HAIRLINE_CHAIN:
        x = int(lm[idx].x * w)
        y = min(int(lm[idx].y * h), y_bottom)
        pts.append([x, y])

    forehead_lift = int((0.10 + severity * 0.08) * face_height)
    center_i = HAIRLINE_CHAIN.index(10)
    pts[center_i][1] = max(crown_y, int(lm[10].y * h) - forehead_lift)

    face_w = max(1.0, abs(lm[454].x - lm[234].x) * w)
    expand_x = max(4, int((0.05 + severity * 0.03) * face_w))
    pts[0][0] = max(0, pts[0][0] - expand_x)
    pts[-1][0] = min(w - 1, pts[-1][0] + expand_x)
    if len(pts) > 3:
        pts[1][0] = max(0, pts[1][0] - expand_x // 2)
        pts[-2][0] = min(w - 1, pts[-2][0] + expand_x // 2)

    crown_y = max(0, min(crown_y, min(p[1] for p in pts) - 2))

    mask = np.zeros((h, w), dtype=np.uint8)
    poly = (
        [(0, crown_y), (w - 1, crown_y), (w - 1, pts[-1][1])]
        + [tuple(p) for p in reversed(pts)]
        + [(0, pts[0][1])]
    )
    cv2.fillPoly(mask, [np.array(poly, dtype=np.int32)], 255)

    min_frac = 0.08 + severity * 0.08
    mask = _ensure_min_mask_fraction(mask, w, h, min_frac=min_frac)

    k_w = max(9, int(0.025 * w)) | 1
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, 3))
    mask = cv2.dilate(mask, kernel_h, iterations=1)

    if feather > 0 and feather % 2 == 0:
        feather += 1
    if feather > 0:
        mask = cv2.GaussianBlur(mask, (feather, feather), 0)

    return Image.fromarray(mask)
