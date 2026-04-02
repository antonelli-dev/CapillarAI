import numpy as np
import cv2
from fastapi import HTTPException, UploadFile

# 10 MB — enough for any reasonable portrait; rejects abuse/accidents early.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def read_image_bgr(file: UploadFile) -> np.ndarray:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Imagen demasiado grande (máximo {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    np_img = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Imagen inválida o corrupta")

    return img
