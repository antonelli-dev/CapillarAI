from fastapi import APIRouter, UploadFile, File, HTTPException

from app.api.common import read_image_bgr
from app.deps import get_validator

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Valida la foto tal cual se subiría a /generate (misma comprobación facial sobre la original).
    No aplica rembg aquí: /generate decide fondo tras validar.
    """
    img = await read_image_bgr(file)

    try:
        get_validator().execute(img)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Imagen válida", "valid": True}
