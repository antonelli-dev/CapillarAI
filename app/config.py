import os
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
    # Comma-separated. Empty = no auth on /upload and /generate (development only).
    api_keys: str
    # SQLite path for hashed API keys (scripts/add_api_key.py). Optional; use with API_KEYS for bootstrap.
    api_keys_db: str | None
    # slowapi format, e.g. 60/minute — see docs/INTEGRATION.md
    rate_limit_upload: str
    rate_limit_generate: str
    # development | production — logs a CORS hint in production if cors_origins empty
    environment: str
    # Si está definido, habilita POST/GET/DELETE /v1/admin/keys (cabecera X-Admin-Secret).
    admin_secret: str | None
    # Si > 0: Strict-Transport-Security (solo se envía si la petición es HTTPS o X-Forwarded-Proto: https).
    secure_hsts_max_age: int | None
    secure_hsts_include_subdomains: bool
    secure_hsts_preload: bool


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


@lru_cache
def get_settings() -> Settings:
    pname = ACTIVE_PROFILE if ACTIVE_PROFILE in PROFILES else "launch"
    prof = get_profile(pname)
    _db = os.environ.get("API_KEYS_DB", "").strip()
    _adm = os.environ.get("ADMIN_SECRET", "").strip()
    _hsts_raw = os.environ.get("SECURE_HSTS_MAX_AGE", "").strip()
    _hsts: int | None
    if not _hsts_raw:
        _hsts = None
    else:
        try:
            _hsts = max(0, int(_hsts_raw))
        except ValueError:
            _hsts = None
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
        api_keys=os.environ.get("API_KEYS", "").strip(),
        api_keys_db=_db if _db else None,
        rate_limit_upload=os.environ.get("RATE_LIMIT_UPLOAD", "60/minute"),
        rate_limit_generate=os.environ.get("RATE_LIMIT_GENERATE", "12/minute"),
        environment=os.environ.get("ENVIRONMENT", "development"),
        admin_secret=_adm if _adm else None,
        secure_hsts_max_age=_hsts,
        secure_hsts_include_subdomains=_env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS"),
        secure_hsts_preload=_env_bool("SECURE_HSTS_PRELOAD"),
    )
