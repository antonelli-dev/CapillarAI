from fastapi import APIRouter, UploadFile, File, HTTPException

from app.application.validate_portrait import ValidatePortraitUseCase
from app.api.common import read_image_bgr
from app.deps import get_face_detector

router = APIRouter()

validate_use_case = ValidatePortraitUseCase(get_face_detector())


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    img = await read_image_bgr(file)

    try:
        validate_use_case.execute(img)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Imagen válida", "valid": True}
