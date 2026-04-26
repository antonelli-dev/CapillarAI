"""API endpoints for hairline presets (v1/presets)."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import get_manage_presets_use_case, get_preset_repository

_settings = get_settings()
router = APIRouter(prefix="/presets", tags=["v1"])


class PresetCreateRequest(BaseModel):
    """Create new hairline preset."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    base_profile: str = Field(default="launch", description="launch, maximum_fill, or identity_lock")
    custom_prompt: str = Field(default="", max_length=500, description="Additional prompt text")
    inpaint_strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    guidance_scale: Optional[float] = Field(None, ge=1.0, le=20.0)


class PresetUpdateRequest(BaseModel):
    """Update existing preset."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    custom_prompt: Optional[str] = Field(None, max_length=500)
    inpaint_strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    guidance_scale: Optional[float] = Field(None, ge=1.0, le=20.0)


class PresetResponse(BaseModel):
    """Preset response."""
    preset_id: str
    name: str
    description: str
    base_profile: str
    custom_prompt: str
    inpaint_strength: Optional[float]
    guidance_scale: Optional[float]
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get(
    "",
    response_model=List[PresetResponse],
    summary="List clinic presets",
    description="Get all hairline presets configured for your clinic.",
)
async def list_presets(
    request: Request,
):
    """List all presets for clinic."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    use_case = get_manage_presets_use_case()
    presets = use_case.list_presets(clinic_id)
    
    return [
        PresetResponse(
            preset_id=p.preset_id,
            name=p.name,
            description=p.description,
            base_profile=p.profile_name,
            custom_prompt=p.custom_prompt_extra,
            inpaint_strength=p.inpaint_strength_override,
            guidance_scale=p.guidance_scale_override,
            created_at=p.created_at.isoformat() if p.created_at else None,
            updated_at=p.updated_at.isoformat() if p.updated_at else None,
        )
        for p in presets
    ]


@router.post(
    "",
    response_model=PresetResponse,
    summary="Create new preset",
    description="Create a custom hairline preset for your clinic (e.g., 'Dr. Smith Conservative').",
    status_code=201,
)
@limiter.limit("30/minute")
async def create_preset(
    request: Request,
    data: PresetCreateRequest,
):
    """Create new hairline preset."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    use_case = get_manage_presets_use_case()
    preset = use_case.create_preset(
        clinic_id=clinic_id,
        name=data.name,
        description=data.description,
        base_profile=data.base_profile,
        custom_prompt=data.custom_prompt,
        inpaint_strength=data.inpaint_strength,
        guidance_scale=data.guidance_scale,
    )
    
    return PresetResponse(
        preset_id=preset.preset_id,
        name=preset.name,
        description=preset.description,
        base_profile=preset.profile_name,
        custom_prompt=preset.custom_prompt_extra,
        inpaint_strength=preset.inpaint_strength_override,
        guidance_scale=preset.guidance_scale_override,
        created_at=preset.created_at.isoformat() if preset.created_at else None,
        updated_at=preset.updated_at.isoformat() if preset.updated_at else None,
    )


@router.get(
    "/{preset_id}",
    response_model=PresetResponse,
    summary="Get preset details",
)
async def get_preset(
    preset_id: str,
    request: Request,
):
    """Get specific preset."""
    clinic_id = "default_clinic"
    
    use_case = get_manage_presets_use_case()
    preset = use_case.get_preset(preset_id)
    
    if not preset or preset.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    return PresetResponse(
        preset_id=preset.preset_id,
        name=preset.name,
        description=preset.description,
        base_profile=preset.profile_name,
        custom_prompt=preset.custom_prompt_extra,
        inpaint_strength=preset.inpaint_strength_override,
        guidance_scale=preset.guidance_scale_override,
        created_at=preset.created_at.isoformat() if preset.created_at else None,
        updated_at=preset.updated_at.isoformat() if preset.updated_at else None,
    )


@router.patch(
    "/{preset_id}",
    response_model=PresetResponse,
    summary="Update preset",
)
async def update_preset(
    preset_id: str,
    request: Request,
    data: PresetUpdateRequest,
):
    """Update existing preset."""
    clinic_id = "default_clinic"
    
    # Verify ownership
    repo = get_preset_repository()
    existing = repo.get_by_id(preset_id)
    if not existing or existing.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    use_case = get_manage_presets_use_case()
    preset = use_case.update_preset(
        preset_id=preset_id,
        name=data.name,
        description=data.description,
        custom_prompt=data.custom_prompt,
        inpaint_strength=data.inpaint_strength,
        guidance_scale=data.guidance_scale,
    )
    
    return PresetResponse(
        preset_id=preset.preset_id,
        name=preset.name,
        description=preset.description,
        base_profile=preset.profile_name,
        custom_prompt=preset.custom_prompt_extra,
        inpaint_strength=preset.inpaint_strength_override,
        guidance_scale=preset.guidance_scale_override,
        created_at=preset.created_at.isoformat() if preset.created_at else None,
        updated_at=preset.updated_at.isoformat() if preset.updated_at else None,
    )


@router.delete(
    "/{preset_id}",
    summary="Delete preset",
    status_code=204,
)
async def delete_preset(
    preset_id: str,
    request: Request,
):
    """Delete preset."""
    clinic_id = "default_clinic"
    
    # Verify ownership
    repo = get_preset_repository()
    existing = repo.get_by_id(preset_id)
    if not existing or existing.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    use_case = get_manage_presets_use_case()
    use_case.delete_preset(preset_id)
    
    return None


@router.post(
    "/{preset_id}/set-default",
    summary="Set as default preset",
    description="Set this preset as default for new simulations.",
)
async def set_default_preset(
    preset_id: str,
    request: Request,
):
    """Set preset as default for clinic."""
    clinic_id = "default_clinic"
    
    # Verify ownership
    repo = get_preset_repository()
    existing = repo.get_by_id(preset_id)
    if not existing or existing.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    repo.set_default(clinic_id, preset_id)
    
    return {"status": "set as default"}
