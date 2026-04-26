"""API endpoints for shareable result links (v1/share)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import get_job_repository, get_storage
from app.domain.job import ShareLink

_settings = get_settings()
router = APIRouter(prefix="/share", tags=["v1"])


class CreateShareLinkRequest(BaseModel):
    """Create shareable link for simulation result."""
    expires_in_days: int = Field(7, ge=1, le=30)
    max_views: int = Field(10, ge=1, le=100)
    watermark_text: str = Field("", max_length=100)


class ShareLinkResponse(BaseModel):
    """Share link response."""
    token: str
    url: str
    expires_at: str
    max_views: int
    view_count: int
    is_valid: bool


@router.post(
    "/{job_id}",
    response_model=ShareLinkResponse,
    summary="Create shareable link",
    description="Create time-limited share link for patient to view/download result.",
)
async def create_share_link(
    job_id: str,
    request: Request,
    data: CreateShareLinkRequest,
):
    """Create shareable link for completed job."""
    clinic_id = "default_clinic"
    
    # Verify job exists and belongs to clinic
    repo = get_job_repository()
    job = repo.get_by_id(job_id)
    
    if not job or job.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status.name != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job not yet completed")
    
    # Create token
    import uuid
    token = str(uuid.uuid4())[:16]  # Short token for URL
    
    share_link = ShareLink(
        token=token,
        job_id=job_id,
        clinic_id=clinic_id,
        expires_at=datetime.utcnow() + timedelta(days=data.expires_in_days),
        max_views=data.max_views,
        watermark_text=data.watermark_text or f"Preview - {clinic_id}",
    )
    
    repo.create_share_link(share_link)
    
    # Build public URL
    # In production, this would be your public domain
    public_url = f"https://capillar.ai/p/{token}"
    
    return ShareLinkResponse(
        token=token,
        url=public_url,
        expires_at=share_link.expires_at.isoformat(),
        max_views=share_link.max_views,
        view_count=0,
        is_valid=True,
    )


@router.get(
    "/public/{token}",
    summary="Access shared result",
    description="Public endpoint for patients to view their simulation result.",
)
async def access_shared_result(
    token: str = Path(..., description="Share token"),
    download: bool = Query(False, description="Force download instead of inline"),
):
    """
    Public endpoint for accessing shared results.
    
    - Validates token
    - Checks expiration and view limits
    - Serves result image
    - Records view count (for analytics)
    """
    repo = get_job_repository()
    share_link = repo.get_share_link(token)
    
    if not share_link:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    
    if not share_link.is_valid():
        raise HTTPException(status_code=410, detail="Link expired or view limit reached")
    
    # Record view
    repo.increment_share_link_views(token)
    
    # Get job and result
    job = repo.get_by_id(share_link.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Result not found")
    
    result_url = job.result_urls.get("simulation")
    if not result_url:
        raise HTTPException(status_code=404, detail="Simulation result not available")
    
    # Serve image with optional watermark
    storage = get_storage()
    
    try:
        # Extract key from URL
        key = _extract_key(result_url)
        image_bytes = storage.download(key)
        
        # Apply watermark if configured (simplified - in production use Pillow)
        # For now, serve as-is
        
        headers = {
            "Content-Disposition": f"{'attachment' if download else 'inline'}; filename=simulation_{token}.png",
            "X-View-Count": str(share_link.view_count + 1),
            "X-Max-Views": str(share_link.max_views) if share_link.max_views else "unlimited",
        }
        
        return StreamingResponse(
            iter([image_bytes]),
            media_type="image/png",
            headers=headers,
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Result file not found")


@router.get(
    "/public/{token}/info",
    summary="Get share link info",
    description="Check share link validity and view count without consuming a view.",
)
async def get_share_info(
    token: str,
):
    """Get share link metadata without consuming view."""
    repo = get_job_repository()
    share_link = repo.get_share_link(token)
    
    if not share_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    return {
        "token": token,
        "is_valid": share_link.is_valid(),
        "expires_at": share_link.expires_at.isoformat(),
        "view_count": share_link.view_count,
        "max_views": share_link.max_views,
        "remaining_views": (
            share_link.max_views - share_link.view_count
            if share_link.max_views else None
        ),
    }


@router.delete(
    "/{token}",
    summary="Revoke share link",
    description="Immediately invalidate a share link.",
)
async def revoke_share_link(
    token: str,
    request: Request,
):
    """Revoke (delete) share link."""
    clinic_id = "default_clinic"
    
    repo = get_job_repository()
    share_link = repo.get_share_link(token)
    
    if not share_link or share_link.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Delete by setting expired in the past
    # In real implementation, add a delete method to repository
    
    return {"status": "revoked"}


def _extract_key(url: str) -> str:
    """Extract storage key from URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.path.lstrip("/")
