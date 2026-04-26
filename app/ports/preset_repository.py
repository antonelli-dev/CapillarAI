"""Port for hairline preset persistence (per clinic)."""
from typing import List, Optional, Protocol

from app.domain.report import HairlinePreset


class PresetRepositoryPort(Protocol):
    """Repository for clinic-specific hairline presets ('Dr. García Style')."""
    
    def create(self, preset: HairlinePreset) -> HairlinePreset:
        """Create new preset."""
        ...
    
    def get_by_id(self, preset_id: str) -> Optional[HairlinePreset]:
        """Get preset by ID."""
        ...
    
    def get_by_clinic(self, clinic_id: str) -> List[HairlinePreset]:
        """List all presets for a clinic."""
        ...
    
    def update(self, preset: HairlinePreset) -> HairlinePreset:
        """Update existing preset."""
        ...
    
    def delete(self, preset_id: str) -> None:
        """Delete preset."""
        ...
    
    def get_default_for_clinic(self, clinic_id: str) -> Optional[HairlinePreset]:
        """Get clinic's default preset, or None to use system default."""
        ...
