import numpy as np
import cv2
from fastapi import HTTPException, UploadFile


async def read_image_bgr(file: UploadFile) -> np.ndarray:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    contents = await file.read()
    np_img = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Imagen inválida o corrupta")

    return img
