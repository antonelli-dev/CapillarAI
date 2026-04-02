import io
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.application.generate_hair import GenerateHairUseCase
from app.application.validate_portrait import ValidatePortraitUseCase
from app.api.common import read_image_bgr
from app.deps import get_face_detector, get_generator

logger = logging.getLogger(__name__)

router = APIRouter()

_validate = ValidatePortraitUseCase(get_face_detector())


@router.post("/generate")
async def generate(file: UploadFile = File(...)):
    img = await read_image_bgr(file)

    try:
        validation = _validate.execute(img)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if validation.landmarks is None:
        raise HTTPException(status_code=400, detail="No se pudieron obtener puntos faciales")

    try:
        result_image = GenerateHairUseCase(get_generator()).execute(
            img,
            validation.landmarks,
        )
    except Exception as e:
        logger.exception("Fallo en generación")
        raise HTTPException(
            status_code=500,
            detail="Error al generar la imagen. Inténtalo de nuevo.",
        ) from e

    buf = io.BytesIO()
    result_image.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")
