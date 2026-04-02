from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PortraitValidation:
    ok: bool
    message: str
    landmarks: Optional[Any] = None
