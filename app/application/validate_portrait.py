from app.domain.portrait import PortraitValidation
from app.ports.face_detector import FaceDetectorPort


class ValidatePortraitUseCase:
    def __init__(self, face_detector: FaceDetectorPort):
        self.face_detector = face_detector

    def execute(self, image):
        result = self.face_detector.validate(image)
        if not result.ok:
            raise ValueError(result.message)
        return result
