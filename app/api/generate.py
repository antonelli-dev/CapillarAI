import asyncio
import io

import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.common import MAX_UPLOAD_MB, read_image_bgr
from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import get_validator, run_inference
from app.infrastructure.background_removal import maybe_replace_background_flat
from app.infrastructure.hair_mask import analyze_scalp_lighting, build_hair_mask_from_landmarks

_settings = get_settings()
router = APIRouter(prefix="/generate", tags=["v1"])


@router.post(
    "",
    summary="Generar simulación capilar",
    description=(
        "Inpainting en la zona de cuero cabelludo. Opcional: `seed` entero para "
        "reproducibilidad aproximada entre ejecuciones. "
        f"Máximo **{MAX_UPLOAD_MB} MB** por imagen. Errores frecuentes: "
        "`503` cola llena, `504` timeout de inferencia."
    ),
    responses={
        200: {"description": "PNG generado", "content": {"image/png": {}}},
        400: {"description": "Validación o imagen inválida"},
        401: {"description": "API key faltante o inválida"},
        413: {"description": "Archivo demasiado grande"},
        429: {"description": "Rate limit excedido"},
        503: {"description": "Servidor ocupado (cola GPU llena)"},
        504: {"description": "Inferencia demasiado lenta"},
    },
)
@limiter.limit(_settings.rate_limit_generate)
async def generate(
    request: Request,
    file: UploadFile = File(...),
    seed: int | None = Query(
        None,
        description="Semilla opcional para reproducibilidad (mismo modelo y versión).",
        ge=0,
        le=2**31 - 1,
    ),
):
    _ = request.client  # slowapi requiere Request en la firma para rate limit
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

    result_image = await run_inference(img, validation.landmarks, seed=seed)

    buf = io.BytesIO()
    result_image.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": 'inline; filename="result.png"'},
    )
