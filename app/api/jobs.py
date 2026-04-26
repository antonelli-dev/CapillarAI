"""API endpoints for async simulation jobs (v1/jobs)."""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.common import MAX_UPLOAD_MB
from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import (
    get_create_job_use_case,
    get_job_repository,
    get_process_job_use_case,
)

_settings = get_settings()
router = APIRouter(prefix="/jobs", tags=["v1"])


class JobCreateRequest(BaseModel):
    """Request body for creating async job."""
    webhook_url: Optional[str] = Field(None, description="Callback URL when job completes")
    patient_reference: Optional[str] = Field(None, description="Pseudonymized patient ID")
    preset_id: Optional[str] = Field(None, description="Hairline preset to use")
    seed: Optional[int] = Field(None, ge=0, le=2**31-1)
    consent_given: bool = Field(False, description="Patient GDPR consent")


class JobResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: str
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    result_urls: dict
    error_message: Optional[str]


class BatchJobResponse(BaseModel):
    """Batch job creation response."""
    job_ids: List[str]
    count: int


@router.post(
    "",
    response_model=JobResponse,
    summary="Create async simulation job",
    description=(
        "Submit photo for async processing. Returns job ID immediately. "
        f"Max {MAX_UPLOAD_MB}MB per image. "
        "Results available via GET /jobs/{job_id} or webhook."
    ),
    responses={
        202: {"description": "Job created and queued"},
        400: {"description": "Invalid image or parameters"},
        413: {"description": "File too large"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit(_settings.rate_limit_generate)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    front_image: UploadFile = File(..., description="Frontal portrait photo"),
    donor_image: Optional[UploadFile] = File(None, description="Optional donor area photo"),
    webhook_url: Optional[str] = Query(None),
    patient_reference: Optional[str] = Query(None),
    preset_id: Optional[str] = Query(None),
    seed: Optional[int] = Query(None),
    consent_given: bool = Query(False),
):
    """Create async job for simulation processing."""
    _ = request.client  # For rate limiting
    
    # Get clinic ID from API key (would need to extract from auth context)
    clinic_id = "default_clinic"
    
    # Read raw bytes for storage
    front_bytes = await front_image.read()
    donor_bytes = await donor_image.read() if donor_image else None
    
    # Validate front image (basic check)
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(front_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="Could not decode image")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")
    
    # Create job
    use_case = get_create_job_use_case()
    job = await use_case.execute_single(
        clinic_id=clinic_id,
        front_image_bytes=front_bytes,
        donor_image_bytes=donor_bytes,
        webhook_url=webhook_url,
        patient_reference=patient_reference,
        preset_id=preset_id,
        seed=seed,
        consent_given=consent_given,
    )
    
    # Trigger background processing
    background_tasks.add_task(process_job_worker, job.job_id)
    
    return JobResponse(
        job_id=job.job_id,
        status=job.status.value,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=None,
        completed_at=None,
        result_urls={},
        error_message=None,
    )


@router.post(
    "/batch",
    response_model=BatchJobResponse,
    summary="Create batch simulation jobs",
    description="Submit multiple photos for batch processing.",
)
@limiter.limit(_settings.rate_limit_generate)
async def create_batch_jobs(
    request: Request,
    background_tasks: BackgroundTasks,
    images: List[UploadFile] = File(..., description="Multiple frontal photos"),
    webhook_url: Optional[str] = Query(None),
    preset_id: Optional[str] = Query(None),
):
    """Create batch jobs for multiple images."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    # Read raw bytes for all images
    image_bytes_list = []
    for img in images[:10]:  # Max 10 per batch
        bytes_data = await img.read()
        image_bytes_list.append(bytes_data)
    
    use_case = get_create_job_use_case()
    jobs = await use_case.execute_batch(
        clinic_id=clinic_id,
        images=image_bytes_list,
        webhook_url=webhook_url,
        preset_id=preset_id,
    )
    
    # Trigger background processing for all jobs
    for job in jobs:
        background_tasks.add_task(process_job_worker, job.job_id)
    
    return BatchJobResponse(
        job_ids=[j.job_id for j in jobs],
        count=len(jobs),
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status and results",
    description="Poll for job completion and retrieve result URLs.",
)
async def get_job(
    job_id: str,
    request: Request,
):
    """Get job status and results."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    repo = get_job_repository()
    job = repo.get_by_id(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.clinic_id != clinic_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return JobResponse(
        job_id=job.job_id,
        status=job.status.value,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result_urls=job.result_urls,
        error_message=job.error_message,
    )


@router.get(
    "",
    response_model=List[JobResponse],
    summary="List clinic jobs",
    description="List jobs with optional filtering by status.",
)
async def list_jobs(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List jobs for clinic."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    from app.domain.job import JobStatus
    
    repo = get_job_repository()
    
    status_filter = None
    if status:
        try:
            status_filter = JobStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    jobs = repo.get_by_clinic(clinic_id, status=status_filter, limit=limit, offset=offset)
    
    return [
        JobResponse(
            job_id=j.job_id,
            status=j.status.value,
            created_at=j.created_at.isoformat() if j.created_at else None,
            started_at=j.started_at.isoformat() if j.started_at else None,
            completed_at=j.completed_at.isoformat() if j.completed_at else None,
            result_urls=j.result_urls,
            error_message=j.error_message,
        )
        for j in jobs
    ]


@router.delete(
    "/{job_id}",
    summary="Cancel pending job",
    description="Cancel job if still pending. Completed jobs cannot be cancelled.",
)
async def cancel_job(
    job_id: str,
    request: Request,
):
    """Cancel pending job."""
    clinic_id = "default_clinic"  # Should come from auth context
    
    repo = get_job_repository()
    job = repo.get_by_id(job_id)
    
    if not job or job.clinic_id != clinic_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    from app.domain.job import JobStatus
    
    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}"
        )
    
    repo.update_status(job_id, JobStatus.CANCELLED)
    return {"status": "cancelled"}


# ── Background Worker ─────────────────────────────────────────────────────────

async def process_job_worker(job_id: str) -> None:
    """Background task to process job."""
    use_case = get_process_job_use_case()
    
    # Run in thread pool to avoid blocking event loop
    await asyncio.to_thread(use_case.execute, job_id)
