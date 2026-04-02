from dataclasses import dataclass
from functools import lru_cache

from app.product_profiles import ACTIVE_PROFILE, PROFILES, get_profile


@dataclass(frozen=True)
class Settings:
    model_id: str
    ip_adapter_repo: str
    ip_adapter_subfolder: str
    ip_adapter_weights: str
    use_ip_adapter: bool
    ip_adapter_scale: float
    device: str | None
    inference_max_side: int
    num_inference_steps: int
    inpaint_strength: float
    guidance_scale: float
    cors_origins: str
    log_level: str
    prompt_extra: str
    strong_fill: bool
    min_inpaint_strength: float
    profile: str


@lru_cache
def get_settings() -> Settings:
    pname = ACTIVE_PROFILE if ACTIVE_PROFILE in PROFILES else "launch"
    prof = get_profile(pname)
    return Settings(
        model_id="runwayml/stable-diffusion-inpainting",
        ip_adapter_repo="h94/IP-Adapter",
        ip_adapter_subfolder="models",
        ip_adapter_weights="ip-adapter_sd15.bin",
        use_ip_adapter=prof["use_ip_adapter"],
        ip_adapter_scale=prof["ip_adapter_scale"],
        device=None,
        inference_max_side=704,
        num_inference_steps=prof["num_inference_steps"],
        inpaint_strength=prof["inpaint_strength"],
        guidance_scale=prof["guidance_scale"],
        cors_origins="",
        log_level="INFO",
        prompt_extra="",
        strong_fill=pname == "maximum_fill",
        min_inpaint_strength=prof["min_inpaint_strength"],
        profile=pname,
    )
