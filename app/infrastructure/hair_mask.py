import logging

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


def estimate_hair_loss_severity(image_bgr: np.ndarray, landmarks) -> float:
    """
    Returns a float in [0.0, 1.0]:
      0.0 = full hair coverage (no visible loss)
      1.0 = completely bald scalp

    Algorithm: compare the brightness of the central scalp zone against a skin
    reference sampled near the chin.  Hair is darker than bare skin, so a
    scalp that looks like skin signals baldness.
    """
    lm = landmarks.landmark
    h, w = image_bgr.shape[:2]

    brow_y = max(lm[107].y, lm[336].y) * h
    chin_y = lm[152].y * h
    face_height = max(1.0, chin_y - brow_y)

    # Scalp ROI: center strip from ~55 % of face height above brows down to just above brows.
    scalp_top = max(0, int(brow_y - 0.55 * face_height))
    scalp_bot = max(scalp_top + 4, int(brow_y) - 4)

    # Horizontal: inner 50 % of face width avoids background.
    face_left = lm[234].x * w
    face_right = lm[454].x * w
    cx = (face_left + face_right) / 2
    half = max(1.0, (face_right - face_left) * 0.25)
    roi_left = max(0, int(cx - half))
    roi_right = min(w - 1, int(cx + half))

    if roi_right <= roi_left or scalp_bot <= scalp_top:
        return 0.5

    # Skin reference: strip near the chin (landmark 152).
    skin_top = max(0, int(chin_y - 0.10 * face_height))
    skin_bot = max(skin_top + 4, min(int(chin_y) + 4, h - 1))
    skin_roi = image_bgr[skin_top:skin_bot, roi_left:roi_right]
    scalp_roi = image_bgr[scalp_top:scalp_bot, roi_left:roi_right]

    if skin_roi.size == 0 or scalp_roi.size == 0:
        return 0.5

    skin_brightness = float(cv2.cvtColor(skin_roi, cv2.COLOR_BGR2GRAY).mean())
    scalp_brightness = float(cv2.cvtColor(scalp_roi, cv2.COLOR_BGR2GRAY).mean())

    if skin_brightness < 5:
        return 0.5

    # ratio ≈ 1.0 → scalp same brightness as skin → bald
    # ratio ≈ 0.4–0.6 → scalp much darker → full hair
    ratio = scalp_brightness / skin_brightness

    # Linear map: [0.55 (hair), 0.92 (bald)] → [0.0, 1.0]
    severity = (ratio - 0.55) / (0.92 - 0.55)
    severity = float(np.clip(severity, 0.0, 1.0))

    label = "severa" if severity > 0.65 else "moderada" if severity > 0.35 else "leve"
    logger.info(
        "Alopecia detectada: %.2f (%s) | scalp=%.1f skin=%.1f ratio=%.2f",
        severity,
        label,
        scalp_brightness,
        skin_brightness,
        ratio,
    )
    return severity


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
        Hair-loss severity in [0, 1] from estimate_hair_loss_severity().
        Controls hairline depth, crown height, lateral expansion and min coverage.
    """
    lm = landmarks.landmark
    h, w = height, width

    brow_y = max(lm[107].y, lm[336].y) * h
    chin_y = lm[152].y * h
    face_height = max(1.0, chin_y - brow_y)

    # ── Hairline target ──────────────────────────────────────────────────────
    # mild (0.0) → 24 % above brows (natural high position)
    # severe (1.0) → 12 % above brows (covers the whole large forehead)
    hairline_pct = 0.24 - severity * 0.12
    y_bottom = max(8, int(brow_y - hairline_pct * face_height))

    # ── Crown start ──────────────────────────────────────────────────────────
    # mild → 30 % above forehead landmark | severe → 50 % (bigger bald region)
    forehead_y = lm[10].y * h
    crown_pct = 0.30 + severity * 0.20
    crown_y = max(0, int(forehead_y - crown_pct * face_height))

    pts = []
    for idx in HAIRLINE_CHAIN:
        x = int(lm[idx].x * w)
        y = min(int(lm[idx].y * h), y_bottom)
        pts.append([x, y])

    # Center point lifted to rounded crown arch.
    forehead_lift = int((0.10 + severity * 0.08) * face_height)
    center_i = HAIRLINE_CHAIN.index(10)
    pts[center_i][1] = max(crown_y, int(lm[10].y * h) - forehead_lift)

    # ── Temporal expansion ───────────────────────────────────────────────────
    # Wider for severe loss to capture thinning sides.
    face_w = max(1.0, abs(lm[454].x - lm[234].x) * w)
    expand_x = max(4, int((0.05 + severity * 0.03) * face_w))
    pts[0][0] = max(0, pts[0][0] - expand_x)
    pts[-1][0] = min(w - 1, pts[-1][0] + expand_x)
    if len(pts) > 3:
        pts[1][0] = max(0, pts[1][0] - expand_x // 2)
        pts[-2][0] = min(w - 1, pts[-2][0] + expand_x // 2)

    # Guarantee crown is above every hairline point.
    crown_y = max(0, min(crown_y, min(p[1] for p in pts) - 2))

    mask = np.zeros((h, w), dtype=np.uint8)
    poly = (
        [(0, crown_y), (w - 1, crown_y), (w - 1, pts[-1][1])]
        + [tuple(p) for p in reversed(pts)]
        + [(0, pts[0][1])]
    )
    cv2.fillPoly(mask, [np.array(poly, dtype=np.int32)], 255)

    # Minimum coverage: mild → 8 %, severe → 16 %
    min_frac = 0.08 + severity * 0.08
    mask = _ensure_min_mask_fraction(mask, w, h, min_frac=min_frac)

    # Slight horizontal dilation to reach ear-adjacent zones.
    k_w = max(9, int(0.025 * w)) | 1
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, 3))
    mask = cv2.dilate(mask, kernel_h, iterations=1)

    # Feather edges.
    if feather > 0 and feather % 2 == 0:
        feather += 1
    if feather > 0:
        mask = cv2.GaussianBlur(mask, (feather, feather), 0)

    return Image.fromarray(mask)
