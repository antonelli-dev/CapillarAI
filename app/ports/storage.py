"""Port for file/object storage (S3/MinIO/Azure Blob)."""
from typing import BinaryIO, Optional, Protocol


class StoragePort(Protocol):
    """
    Abstract storage for images, PDFs, and temporary files.
    Supports S3, MinIO, Azure Blob, or local filesystem.
    """
    
    def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Upload file to storage.
        
        Returns:
            Public or presigned URL for access
        """
        ...
    
    def download(self, key: str) -> bytes:
        """Download file content."""
        ...
    
    def get_presigned_url(
        self,
        key: str,
        expiration_seconds: int = 3600,
    ) -> str:
        """Get temporary access URL (for share links)."""
        ...
    
    def delete(self, key: str) -> None:
        """Delete file (GDPR erasure)."""
        ...
    
    def exists(self, key: str) -> bool:
        """Check if file exists."""
        ...
    
    def generate_key(
        self,
        clinic_id: str,
        patient_reference: str,
        file_type: str,
        extension: str,
    ) -> str:
        """
        Generate standardized key path.
        E.g.: clinics/{clinic_id}/{patient_reference}/{file_type}_{timestamp}.{ext}
        """
        ...
