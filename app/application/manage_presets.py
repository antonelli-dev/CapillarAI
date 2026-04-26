"""Use case: CRUD operations for clinic hairline presets."""
import logging
from datetime import datetime
from typing import List, Optional

from app.domain.report import HairlinePreset
from app.ports.preset_repository import PresetRepositoryPort

logger = logging.getLogger(__name__)


class ManagePresetsUseCase:
    """
    Manage clinic-specific hairline presets.
    Presets allow clinics to define their signature styles (e.g., "Dr. García conservative").
    """
    
    def __init__(self, preset_repository: PresetRepositoryPort):
        self.preset_repository = preset_repository
    
    def create_preset(
        self,
        clinic_id: str,
        name: str,
        description: str,
        base_profile: str = "launch",
        custom_prompt: str = "",
        inpaint_strength: Optional[float] = None,
        guidance_scale: Optional[float] = None,
    ) -> HairlinePreset:
        """
        Create new hairline preset for clinic.
        
        Args:
            clinic_id: Organization identifier
            name: Display name (e.g., "Conservative Hairline")
            description: Detailed description for clinic staff
            base_profile: Base system profile (launch, maximum_fill, identity_lock)
            custom_prompt: Additional prompt text for SD
            inpaint_strength: Override default strength (0.0-1.0)
            guidance_scale: Override default CFG (1.0-20.0)
        """
        import uuid
        
        now = datetime.utcnow()
        preset = HairlinePreset(
            preset_id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            name=name,
            description=description,
            profile_name=base_profile,
            custom_prompt_extra=custom_prompt,
            inpaint_strength_override=inpaint_strength,
            guidance_scale_override=guidance_scale,
            created_at=now,
            updated_at=now,
        )
        
        return self.preset_repository.create(preset)
    
    def list_presets(self, clinic_id: str) -> List[HairlinePreset]:
        """Get all presets for a clinic."""
        return self.preset_repository.get_by_clinic(clinic_id)
    
    def get_preset(self, preset_id: str) -> Optional[HairlinePreset]:
        """Get specific preset by ID."""
        return self.preset_repository.get_by_id(preset_id)
    
    def update_preset(
        self,
        preset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        inpaint_strength: Optional[float] = None,
        guidance_scale: Optional[float] = None,
    ) -> HairlinePreset:
        """Update existing preset."""
        preset = self.preset_repository.get_by_id(preset_id)
        if not preset:
            raise ValueError(f"Preset {preset_id} not found")
        
        # Build updated preset (dataclass is frozen, create new)
        updated = HairlinePreset(
            preset_id=preset.preset_id,
            clinic_id=preset.clinic_id,
            name=name if name is not None else preset.name,
            description=description if description is not None else preset.description,
            profile_name=preset.profile_name,
            custom_prompt_extra=custom_prompt if custom_prompt is not None else preset.custom_prompt_extra,
            inpaint_strength_override=inpaint_strength if inpaint_strength is not None else preset.inpaint_strength_override,
            guidance_scale_override=guidance_scale if guidance_scale is not None else preset.guidance_scale_override,
            created_at=preset.created_at,
            updated_at=datetime.utcnow(),
        )
        
        return self.preset_repository.update(updated)
    
    def delete_preset(self, preset_id: str) -> None:
        """Delete preset."""
        self.preset_repository.delete(preset_id)
    
    def get_effective_params(self, preset_id: Optional[str]) -> dict:
        """
        Get effective parameters for simulation.
        Merges preset overrides with base profile defaults.
        """
        if not preset_id:
            # Use system default (from product_profiles.py)
            return {"profile": "launch"}
        
        preset = self.preset_repository.get_by_id(preset_id)
        if not preset:
            raise ValueError(f"Preset {preset_id} not found")
        
        params = {"profile": preset.profile_name}
        
        if preset.inpaint_strength_override is not None:
            params["inpaint_strength"] = preset.inpaint_strength_override
        
        if preset.guidance_scale_override is not None:
            params["guidance_scale"] = preset.guidance_scale_override
        
        if preset.custom_prompt_extra:
            params["prompt_extra"] = preset.custom_prompt_extra
        
        return params
