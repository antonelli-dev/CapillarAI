import asyncio
import io

import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.api.common import read_image_bgr
from app.deps import get_validator, run_inference
from app.infrastructure.background_removal import maybe_replace_background_flat
from app.infrastructure.hair_mask import analyze_scalp_lighting, build_hair_mask_from_landmarks

router = APIRouter()


@router.post("/generate")
async def generate(file: UploadFile = File(...)):
    img = await read_image_bgr(file)

    try:
        validation = get_validator().execute(img)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if validation.landmarks is None:
        raise HTTPException(status_code=400, detail="No se pudieron obtener puntos faciales")

    lighting = analyze_scalp_lighting(img, validation.landmarks)
    h, w = img.shape[:2]
    mask_pil = build_hair_mask_from_landmarks(
        w, h, validation.landmarks, severity=lighting.severity
    )
    ma = np.asarray(mask_pil)
    if ma.ndim == 3:
        ma = ma[:, :, 0]
    mfrac = float(np.mean(ma > 127))
    img, _ = await asyncio.to_thread(
        maybe_replace_background_flat, img, lighting.severity, mfrac
    )

    result_image = await run_inference(img, validation.landmarks)

    buf = io.BytesIO()
    result_image.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=\"result.png\""},
    )
