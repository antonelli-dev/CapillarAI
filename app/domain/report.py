"""Domain entities for medical PDF reports and analysis."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SeverityLevel(Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class DonorViability(Enum):
    VIABLE_SINGLE_SESSION = "viable_single_session"
    VIABLE_MULTIPLE_SESSIONS = "viable_multiple_sessions"
    MARGINAL = "marginal"
    NOT_RECOMMENDED = "not_recommended"


@dataclass(frozen=True)
class ScalpAnalysis:
    severity: SeverityLevel
    brightness_score: float
    contrast_score: float
    coverage_area_cm2: Optional[float] = None


@dataclass(frozen=True)
class DonorAnalysis:
    density_score: float  # 0-10 scale
    estimated_grafts: int
    coverage_area_cm2: float
    hair_caliber_mm: Optional[float] = None
    recommendation: DonorViability = DonorViability.VIABLE_SINGLE_SESSION
    confidence: float = 0.0
    reasoning: str = ""


@dataclass(frozen=True)
class SimulationParameters:
    profile_name: str
    num_inference_steps: int
    inpaint_strength: float
    guidance_scale: float
    seed: Optional[int] = None
    use_ip_adapter: bool = False
    ip_adapter_scale: float = 0.0


@dataclass
class MedicalReport:
    report_id: str
    clinic_id: str
    patient_reference: Optional[str]  # pseudonymized
    created_at: datetime
    original_image: bytes
    simulation_image: bytes
    scalp_analysis: ScalpAnalysis
    simulation_params: SimulationParameters
    donor_analysis: Optional[DonorAnalysis] = None
    disclaimer_text: str = ""
    clinic_logo: Optional[bytes] = None
    clinic_name: str = ""

    def total_estimated_grafts(self) -> Optional[int]:
        """Calculate total grafts needed based on recipient area."""
        if self.donor_analysis is None or self.scalp_analysis.coverage_area_cm2 is None:
            return None
        # Industry standard: 20-30 grafts/cm² for good density
        grafts_per_cm2 = 25
        return int(self.scalp_analysis.coverage_area_cm2 * grafts_per_cm2)


@dataclass(frozen=True)
class HairlinePreset:
    preset_id: str
    clinic_id: str
    name: str
    description: str
    profile_name: str
    custom_prompt_extra: str = ""
    inpaint_strength_override: Optional[float] = None
    guidance_scale_override: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
