from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.api.rate_limit_ext import limiter
from app.api.common import MAX_UPLOAD_MB
from app.config import get_settings
from app.deps import get_validator

_settings = get_settings()
router = APIRouter(prefix="/upload", tags=["v1"])


@router.post(
    "",
    summary="Validar retrato",
    description=(
        "Comprueba rostro, encuadre y luz (misma lógica que antes de generar). "
        f"Máximo **{MAX_UPLOAD_MB} MB** por imagen."
    ),
    responses={
        200: {"description": "Imagen válida para generación"},
        400: {"description": "Validación fallida (mensaje en `detail`)"},
        401: {"description": "API key faltante o inválida"},
        413: {"description": "Archivo demasiado grande"},
        429: {"description": "Rate limit excedido"},
    },
)
@limiter.limit(_settings.rate_limit_upload)
async def upload(request: Request, file: UploadFile = File(...)):
    from app.api.common import read_image_bgr

    img = await read_image_bgr(file)

    try:
        get_validator().execute(img)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse({"message": "Imagen válida", "valid": True})
