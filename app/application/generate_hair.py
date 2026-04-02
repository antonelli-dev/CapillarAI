from PIL import Image

from app.ports.image_generator import ImageGeneratorPort


class GenerateHairUseCase:
    def __init__(self, generator: ImageGeneratorPort):
        self.generator = generator

    def execute(self, image_bgr, face_landmarks) -> Image.Image:
        return self.generator.generate(image_bgr, face_landmarks)
