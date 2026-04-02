from typing import Protocol

import numpy as np

from app.domain.portrait import PortraitValidation


class FaceDetectorPort(Protocol):
    def validate(self, image: np.ndarray) -> PortraitValidation:
        ...
