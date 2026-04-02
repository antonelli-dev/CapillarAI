import logging

import cv2
import numpy as np
import torch
from diffusers import StableDiffusionInpaintPipeline
from PIL import Image

from app.config import Settings
from app.infrastructure.hair_mask import (
    analyze_scalp_lighting,
    build_hair_mask_from_landmarks,
    build_hairline_band_mask,
)
from app.infrastructure.hair_preprocess import soften_specular_bgr

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
        core = (
            "same person same face same skin tone, "
            "hair color matching temples and sideburns, consistent natural tone, "
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
            "wig, fake hair, pluggy grafts, cartoon, watermark, low quality, "
            "green tint, teal cast, gray green, muddy color, color cast, "
            "unnatural hair color, wrong hair color"
        )

    def _hairline_refinement_prompt(self) -> str:
        return self._clip_safe(
            "same person same face, soft natural hairline blend forehead to hair, "
            "seamless transition, photorealistic, subtle hair strands"
        )

    def generate(self, image_bgr: np.ndarray, face_landmarks) -> Image.Image:
        lighting = analyze_scalp_lighting(image_bgr, face_landmarks)
        severity = lighting.severity

        # CLAHE helps specular outdoor shots but shifts color on extreme alopecia — skip then.
        _CLAHE_SEVERITY_MAX = 0.85
        work_bgr = image_bgr
        if lighting.hard_lighting and severity <= _CLAHE_SEVERITY_MAX:
            work_bgr = soften_specular_bgr(image_bgr)
            logger.info(
                "Luz dura detectada: preprocesado CLAHE suave (severidad %.2f ≤ %.2f)",
                severity,
                _CLAHE_SEVERITY_MAX,
            )
        elif lighting.hard_lighting and severity > _CLAHE_SEVERITY_MAX:
            logger.info(
                "Luz dura pero severidad %.2f > %.2f: CLAHE omitido (evitar deriva de color)",
                severity,
                _CLAHE_SEVERITY_MAX,
            )

        pil = Image.fromarray(cv2.cvtColor(work_bgr, cv2.COLOR_BGR2RGB))
        orig_size = pil.size

        w, h = pil.size
        max_side = self.settings.inference_max_side
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            w, h = int(w * scale), int(h * scale)
            pil = pil.resize((w, h), _LANCZOS)

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

        # Second pass: hairline band — skip on huge masks or extreme severity (reduces color drift).
        _REFINE_SEVERITY_MAX = 0.85
        _REFINE_MFRAC_MAX = 0.22
        hairline_pixels = 0
        if (
            lighting.hard_lighting
            and mfrac >= 0.12
            and mfrac <= _REFINE_MFRAC_MAX
            and severity <= _REFINE_SEVERITY_MAX
        ):
            r_small = result.resize((w, h), _LANCZOS)
            band = build_hairline_band_mask(mask_arr)
            hairline_pixels = int(np.sum(band > 127))
            if hairline_pixels >= 800:
                logger.info(
                    "Segundo paso línea de pelo: %s píxeles (refinación borde)",
                    hairline_pixels,
                )
                band_pil = Image.fromarray(band).convert("L")
                refine_steps = max(32, self.settings.num_inference_steps // 2)
                refine_kwargs = {
                    "prompt": self._hairline_refinement_prompt(),
                    "negative_prompt": (
                        "harsh edge, visible line, different person, wig, bald, "
                        "cartoon, low quality, green tint, muddy color, color cast"
                    ),
                    "image": r_small,
                    "mask_image": band_pil,
                    "strength": 0.44,
                    "num_inference_steps": refine_steps,
                    "guidance_scale": min(8.5, self.settings.guidance_scale),
                    "num_images_per_prompt": 1,
                    "padding_mask_crop": 96,
                }
                if self._ip_adapter_loaded:
                    refine_kwargs["ip_adapter_image"] = r_small
                result = self.pipe(**refine_kwargs).images[0]
            else:
                logger.debug("Segundo paso omitido: banda línea pelo demasiado pequeña")
        elif lighting.hard_lighting and (
            mfrac > _REFINE_MFRAC_MAX or severity > _REFINE_SEVERITY_MAX
        ):
            logger.info(
                "Segundo paso línea de pelo omitido (mfrac=%.2f severidad=%.2f; evitar deriva de color)",
                mfrac,
                severity,
            )

        if result.size != orig_size:
            result = result.resize(orig_size, _LANCZOS)

        return result
