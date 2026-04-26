"""SQLite implementation of PresetRepositoryPort."""
import json
import logging
import sqlite3
from datetime import datetime
from typing import List, Optional

from app.domain.report import HairlinePreset
from app.ports.preset_repository import PresetRepositoryPort

logger = logging.getLogger(__name__)


class SQLitePresetRepository(PresetRepositoryPort):
    """
    SQLite-based preset repository.
    Stores clinic-specific hairline presets.
    """
    
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hairline_presets (
                    preset_id TEXT PRIMARY KEY,
                    clinic_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    profile_name TEXT NOT NULL,
                    custom_prompt_extra TEXT DEFAULT '',
                    inpaint_strength_override REAL,
                    guidance_scale_override REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_default BOOLEAN DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS clinic_id_idx ON hairline_presets (clinic_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS is_default_idx ON hairline_presets (clinic_id, is_default)")
    
    def create(self, preset: HairlinePreset) -> HairlinePreset:
        """Create new preset."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO hairline_presets (
                    preset_id, clinic_id, name, description, profile_name,
                    custom_prompt_extra, inpaint_strength_override, guidance_scale_override,
                    created_at, updated_at, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preset.preset_id,
                    preset.clinic_id,
                    preset.name,
                    preset.description,
                    preset.profile_name,
                    preset.custom_prompt_extra,
                    preset.inpaint_strength_override,
                    preset.guidance_scale_override,
                    preset.created_at or datetime.utcnow(),
                    preset.updated_at or datetime.utcnow(),
                    False,
                )
            )
        return preset
    
    def get_by_id(self, preset_id: str) -> Optional[HairlinePreset]:
        """Get preset by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM hairline_presets WHERE preset_id = ?",
                (preset_id,)
            ).fetchone()
            
            if row:
                return self._row_to_preset(row)
            return None
    
    def get_by_clinic(self, clinic_id: str) -> List[HairlinePreset]:
        """List all presets for a clinic."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM hairline_presets WHERE clinic_id = ? ORDER BY created_at DESC",
                (clinic_id,)
            ).fetchall()
            return [self._row_to_preset(row) for row in rows]
    
    def update(self, preset: HairlinePreset) -> HairlinePreset:
        """Update existing preset."""
        now = datetime.utcnow()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE hairline_presets SET
                    name = ?,
                    description = ?,
                    profile_name = ?,
                    custom_prompt_extra = ?,
                    inpaint_strength_override = ?,
                    guidance_scale_override = ?,
                    updated_at = ?
                WHERE preset_id = ?
                """,
                (
                    preset.name,
                    preset.description,
                    preset.profile_name,
                    preset.custom_prompt_extra,
                    preset.inpaint_strength_override,
                    preset.guidance_scale_override,
                    now,
                    preset.preset_id,
                )
            )
        
        # Return updated preset
        return self.get_by_id(preset.preset_id)
    
    def delete(self, preset_id: str) -> None:
        """Delete preset."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM hairline_presets WHERE preset_id = ?",
                (preset_id,)
            )
    
    def get_default_for_clinic(self, clinic_id: str) -> Optional[HairlinePreset]:
        """Get clinic's default preset."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM hairline_presets WHERE clinic_id = ? AND is_default = 1 LIMIT 1",
                (clinic_id,)
            ).fetchone()
            
            if row:
                return self._row_to_preset(row)
            return None
    
    def set_default(self, clinic_id: str, preset_id: str) -> None:
        """Set a preset as default for clinic (clear others first)."""
        with sqlite3.connect(self.db_path) as conn:
            # Clear existing default
            conn.execute(
                "UPDATE hairline_presets SET is_default = 0 WHERE clinic_id = ?",
                (clinic_id,)
            )
            # Set new default
            conn.execute(
                "UPDATE hairline_presets SET is_default = 1 WHERE preset_id = ?",
                (preset_id,)
            )
    
    def _row_to_preset(self, row: sqlite3.Row) -> HairlinePreset:
        """Convert DB row to domain object."""
        return HairlinePreset(
            preset_id=row["preset_id"],
            clinic_id=row["clinic_id"],
            name=row["name"],
            description=row["description"] or "",
            profile_name=row["profile_name"],
            custom_prompt_extra=row["custom_prompt_extra"] or "",
            inpaint_strength_override=row["inpaint_strength_override"],
            guidance_scale_override=row["guidance_scale_override"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
