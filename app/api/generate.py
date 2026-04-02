import io
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.api.common import read_image_bgr
from app.deps import get_validator, run_inference

logger = logging.getLogger(__name__)

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

    result_image = await run_inference(img, validation.landmarks)

    buf = io.BytesIO()
    result_image.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=\"result.png\""},
    )
