"""
Parámetros de inferencia por perfil. Cambia ACTIVE_PROFILE aquí si lo necesitas
("launch" | "maximum_fill" | "identity_lock"). Sin .env: todo en código.
"""

from __future__ import annotations

from typing import TypedDict


class InferenceProfile(TypedDict):
    use_ip_adapter: bool
    ip_adapter_scale: float
    inpaint_strength: float
    guidance_scale: float
    min_inpaint_strength: float
    num_inference_steps: int


PROFILES: dict[str, InferenceProfile] = {
    "launch": {
        "use_ip_adapter": False,
        "ip_adapter_scale": 0.35,
        "inpaint_strength": 0.95,
        "guidance_scale": 9.25,
        "min_inpaint_strength": 0.94,
        "num_inference_steps": 55,
    },
    "maximum_fill": {
        "use_ip_adapter": False,
        "ip_adapter_scale": 0.35,
        "inpaint_strength": 0.97,
        "guidance_scale": 9.5,
        "min_inpaint_strength": 0.96,
        "num_inference_steps": 58,
    },
    "identity_lock": {
        "use_ip_adapter": True,
        "ip_adapter_scale": 0.38,
        "inpaint_strength": 0.90,
        "guidance_scale": 8.9,
        "min_inpaint_strength": 0.88,
        "num_inference_steps": 55,
    },
}

DEFAULT_PROFILE = "launch"

# Perfil usado al arrancar (editar solo esta línea para cambiar comportamiento).
ACTIVE_PROFILE: str = "launch"


def get_profile(name: str) -> InferenceProfile:
    return PROFILES.get(name, PROFILES[DEFAULT_PROFILE])
