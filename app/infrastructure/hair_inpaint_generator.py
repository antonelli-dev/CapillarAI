import logging

import cv2
import numpy as np
import torch
from diffusers import StableDiffusionInpaintPipeline
from PIL import Image

from app.config import Settings
from app.infrastructure.hair_mask import build_hair_mask_from_landmarks, estimate_hair_loss_severity

logger = logging.getLogger(__name__)

try:
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    _LANCZOS = Image.LANCZOS


def _resolve_device(settings: Settings) -> str:
    if settings.device:
        return settings.device
    return "cuda" if torch.cuda.is_available() else "cpu"


class HairInpaintGenerator:
    """
    Perfil por defecto en app/product_profiles.py (launch: sin IP-Adapter para que el
    inpainting no quede anclado a la calvicie). IP solo en perfil identity_lock.
    Prompts acotados al límite CLIP (~77 tokens).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = _resolve_device(settings)
        self.torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

        logger.info(
            "Cargando Stable Diffusion Inpainting [%s] en %s (%s)",
            settings.profile,
            self.device,
            self.torch_dtype,
        )
        logger.info(
            "Inferencia: IP=%s scale=%.2f strength=%.2f min=%.2f CFG=%.2f",
            settings.use_ip_adapter,
            settings.ip_adapter_scale,
            settings.inpaint_strength,
            settings.min_inpaint_strength,
            settings.guidance_scale,
        )

        self.pipe = StableDiffusionInpaintPipeline.from_pretrained(
            settings.model_id,
            torch_dtype=self.torch_dtype,
            safety_checker=None,
        )
        self.pipe = self.pipe.to(self.device)

        if self.device == "cuda":
            self.pipe.enable_vae_slicing()
            self.pipe.enable_attention_slicing()

        self._ip_adapter_loaded = False
        if settings.use_ip_adapter:
            try:
                self.pipe.load_ip_adapter(
                    settings.ip_adapter_repo,
                    subfolder=settings.ip_adapter_subfolder,
                    weight_name=settings.ip_adapter_weights,
                )
                self.pipe.set_ip_adapter_scale(settings.ip_adapter_scale)
                self._ip_adapter_loaded = True
                logger.info(
                    "IP-Adapter activo (scale=%s)",
                    settings.ip_adapter_scale,
                )
            except Exception as e:
                logger.warning(
                    "No se pudo cargar IP-Adapter (se continúa sin él): %s",
                    e,
                )

    # CLIP (SD 1.5) admite como máximo 77 tokens; prompts largos se truncan al final.
    _MAX_PROMPT_WORDS = 58

    def _clip_safe(self, text: str) -> str:
        words = text.split()
        if len(words) <= self._MAX_PROMPT_WORDS:
            return text
        logger.warning(
            "Prompt truncado a %s palabras (límite CLIP ~77 tokens): %s…",
            self._MAX_PROMPT_WORDS,
            " ".join(words[:12]),
        )
        return " ".join(words[: self._MAX_PROMPT_WORDS])

    def _build_prompt(self) -> str:
        # Direct description of the desired OUTPUT, not instructions to the model.
        core = (
            "same person same face same skin tone, "
            "full head of hair 12 months after FUE hair transplant, "
            "natural grown out result 8-10cm length, "
            "natural hairline above forehead, scalp completely covered, "
            "photorealistic portrait, professional photo"
        )
        if self.settings.strong_fill:
            core += ", thick maximum density full coverage all over scalp"
        extra = self.settings.prompt_extra.strip()
        combined = f"{core}, {extra}" if extra else core
        return self._clip_safe(combined)

    @staticmethod
    def _build_negative_prompt() -> str:
        return (
            "bald, balding, thinning, bald spot, receding hairline, no hair, "
            "sparse hair, visible scalp, different person, changed face, "
            "wig, fake hair, pluggy grafts, cartoon, watermark, low quality"
        )

    def generate(self, image_bgr: np.ndarray, face_landmarks) -> Image.Image:
        pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        orig_size = pil.size

        w, h = pil.size
        max_side = self.settings.inference_max_side
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            w, h = int(w * scale), int(h * scale)
            pil = pil.resize((w, h), _LANCZOS)

        # Measure severity on the original full-res image for better accuracy.
        severity = estimate_hair_loss_severity(image_bgr, face_landmarks)

        mask = build_hair_mask_from_landmarks(w, h, face_landmarks, severity=severity)

        mask_arr = np.asarray(mask)
        if mask_arr.ndim == 3:
            mask_arr = mask_arr[:, :, 0]
        mfrac = float(np.mean(mask_arr > 127))
        logger.info(
            "Máscara inpainting: %.1f%% píxeles a repintar | severidad=%.2f",
            100.0 * mfrac,
            severity,
        )
        if mfrac < 0.02:
            logger.warning(
                "Máscara muy pequeña (%.1f%%); el cambio puede ser casi invisible.",
                100.0 * mfrac,
            )

        raw_strength = self.settings.inpaint_strength
        strength = max(raw_strength, self.settings.min_inpaint_strength)
        # For severe or moderate loss force near-maximum strength so the model
        # fully overrides sparse/thin hair instead of preserving it.
        if severity >= 0.45:
            strength = max(strength, 0.97)
        if strength > raw_strength:
            logger.info(
                "Inpaint strength %.2f → %.2f (ajuste por severidad %.2f)",
                raw_strength,
                strength,
                severity,
            )

        call_kwargs = {
            "prompt": self._build_prompt(),
            "negative_prompt": self._build_negative_prompt(),
            "image": pil,
            "mask_image": mask,
            "strength": strength,
            "num_inference_steps": self.settings.num_inference_steps,
            "guidance_scale": self.settings.guidance_scale,
            "num_images_per_prompt": 1,
            "padding_mask_crop": 128,
        }
        if self._ip_adapter_loaded:
            call_kwargs["ip_adapter_image"] = pil

        result = self.pipe(**call_kwargs).images[0]

        if result.size != orig_size:
            result = result.resize(orig_size, _LANCZOS)

        return result
