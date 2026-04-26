"""Local filesystem implementation of StoragePort (for dev/MVP)."""
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Optional

from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class LocalStorage(StoragePort):
    """
    Local filesystem storage for development and MVP.
    Replace with S3Storage or MinIOStorage for production.
    """
    
    def __init__(self, base_path: str = "./storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> str:
        """Upload file to local storage."""
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if isinstance(data, bytes):
            file_path.write_bytes(data)
        else:
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(data, f)
        
        # Store metadata alongside file
        if metadata:
            meta_path = file_path.with_suffix(file_path.suffix + '.meta')
            import json
            meta_path.write_text(json.dumps(metadata, default=str))
        
        # Return file:// URL for local access
        return f"file://{file_path.absolute()}"
    
    def download(self, key: str) -> bytes:
        """Download file content."""
        # Handle both file:// URLs and plain keys
        if key.startswith("file://"):
            key = key[7:]
            if key.startswith("/"):
                key = key[1:]
        
        file_path = self.base_path / key
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        
        return file_path.read_bytes()
    
    def get_presigned_url(
        self,
        key: str,
        expiration_seconds: int = 3600,
    ) -> str:
        """
        For local storage, return direct file URL.
        In production, this would generate signed S3/MinIO URLs.
        """
        file_path = self.base_path / key
        return f"file://{file_path.absolute()}"
    
    def delete(self, key: str) -> None:
        """Delete file."""
        if key.startswith("file://"):
            key = key[7:]
            if key.startswith("/"):
                key = key[1:]
        
        file_path = self.base_path / key
        if file_path.exists():
            file_path.unlink()
            # Also delete metadata if exists
            meta_path = file_path.with_suffix(file_path.suffix + '.meta')
            if meta_path.exists():
                meta_path.unlink()
    
    def exists(self, key: str) -> bool:
        """Check if file exists."""
        if key.startswith("file://"):
            key = key[7:]
            if key.startswith("/"):
                key = key[1:]
        
        file_path = self.base_path / key
        return file_path.exists()
    
    def generate_key(
        self,
        clinic_id: str,
        patient_reference: str,
        file_type: str,
        extension: str,
    ) -> str:
        """Generate standardized key path."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        ext = extension.lstrip('.')
        
        # Sanitize IDs for filesystem
        safe_clinic = self._sanitize(clinic_id)
        safe_patient = self._sanitize(patient_reference)
        
        return f"clinics/{safe_clinic}/{safe_patient}/{file_type}_{timestamp}.{ext}"
    
    def _sanitize(self, value: str) -> str:
        """Sanitize string for filesystem use."""
        # Replace problematic characters
        safe = value.replace('/', '_').replace('\\', '_').replace(':', '_')
        return safe[:50]  # Limit length
