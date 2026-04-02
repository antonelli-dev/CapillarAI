"""Mild exposure flattening for harsh outdoor / specular scalp (inpaint input only)."""

import cv2
import numpy as np


def soften_specular_bgr(image_bgr: np.ndarray, blend_original: float = 0.52) -> np.ndarray:
    """
    CLAHE on LAB L channel, blended back with the original to avoid plastic skin.

    blend_original: weight of original (0.52 => ~half each); higher = subtler correction.
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.3, tileGridSize=(8, 8))
    l2 = clahe.apply(l_ch)
    merged = cv2.merge([l2, a_ch, b_ch])
    corrected = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    out = cv2.addWeighted(
        image_bgr.astype(np.float32),
        blend_original,
        corrected.astype(np.float32),
        1.0 - blend_original,
        0,
    )
    return np.clip(out, 0, 255).astype(np.uint8)
