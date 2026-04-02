from typing import Any, Protocol

import numpy as np
from PIL import Image


class ImageGeneratorPort(Protocol):
    def generate(self, image_bgr: np.ndarray, face_landmarks: Any) -> Image.Image:
        ...
