"""API endpoints for donor area viability analysis (v1/donor-analysis)."""
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.common import read_image_bgr
from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import get_analyze_donor_use_case

_settings = get_settings()
router = APIRouter(prefix="/donor-analysis", tags=["v1"])


class ZoneBreakdown(BaseModel):
    """Individual zone analysis results."""
    zone_name: str = Field(..., description="Zone name (coronilla, left_temporal, right_temporal)")
    density_score: float = Field(..., ge=0, le=10, description="Hair density 0-10")
    estimated_grafts: int = Field(..., description="Estimated grafts for this zone")
    coverage_area_cm2: float = Field(..., description="Zone coverage area")


class DonorAnalysisResponse(BaseModel):
    """Donor area analysis results."""
    density_score: float = Field(..., ge=0, le=10, description="Average hair density 0-10")
    estimated_grafts: int = Field(..., description="Total estimated grafts (all zones)")
    coverage_area_cm2: float = Field(..., description="Total donor coverage area in cm²")
    hair_caliber_mm: Optional[float] = Field(None, description="Average hair thickness")
    recommendation: str = Field(..., description="Viability recommendation")
    confidence: float = Field(..., ge=0, le=1, description="Analysis confidence")
    reasoning: str = Field(..., description="Detailed explanation")
    match_score: Optional[float] = Field(None, description="Match score if recipient area provided")
    zones_analyzed: int = Field(..., description="Number of zones analyzed")
    zone_breakdown: list[ZoneBreakdown] = Field([], description="Individual zone results")


class DonorAnalysisRequest(BaseModel):
    """Request for donor analysis with optional recipient area."""
    recipient_area_cm2: Optional[float] = Field(None, gt=0, description="Recipient bald area in cm²")


@router.post(
    "",
    response_model=DonorAnalysisResponse,
    summary="Analyze donor area viability",
    description=(
        "Analyze donor area (back of head) to estimate available grafts and viability. "
        "CPU-only operation, no GPU required. Fast response (<1s)."
    ),
    responses={
        200: {"description": "Analysis completed"},
        400: {"description": "Invalid image"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit(_settings.rate_limit_upload)
async def analyze_donor(
    request: Request,
    coronilla_image: UploadFile = File(..., description="Back of head (coronilla) - main donor area"),
    left_temporal_image: Optional[UploadFile] = File(None, description="Left side/temporal area"),
    right_temporal_image: Optional[UploadFile] = File(None, description="Right side/temporal area"),
    recipient_area_cm2: Optional[float] = Query(
        None,
        gt=0,
        description="Optional recipient bald area for match calculation (cm²)"
    ),
):
    """
    Analyze donor area for hair transplant viability.
    
    Analyzes multiple donor zones:
    - Coronilla (back of head) - REQUIRED
    - Left temporal (side) - optional
    - Right temporal (side) - optional
    
    Sums graft estimates from all zones for total availability.
    
    No GPU required - runs entirely on CPU via OpenCV.
    """
    clinic_id = "default_clinic"  # Should come from auth context
    
    # Read all donor images
    images = {
        "coronilla": await coronilla_image.read(),
    }
    
    if left_temporal_image:
        images["left_temporal"] = await left_temporal_image.read()
    if right_temporal_image:
        images["right_temporal"] = await right_temporal_image.read()
    
    # Run analysis
    use_case = get_analyze_donor_use_case()
    
    try:
        result = await use_case.execute_multi_zone(
            clinic_id=clinic_id,
            donor_images=images,
            recipient_area_cm2=recipient_area_cm2,
        )
        analysis = result.combined
        zone_breakdown = result.zone_breakdown
        zones_count = result.zones_count
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Calculate match score if recipient area provided
    match_score = None
    if recipient_area_cm2:
        match_score = use_case.donor_analyzer.calculate_match_score(
            analysis,
            recipient_area_cm2,
        )
    
    return DonorAnalysisResponse(
        density_score=analysis.density_score,
        estimated_grafts=analysis.estimated_grafts,
        coverage_area_cm2=analysis.coverage_area_cm2,
        hair_caliber_mm=analysis.hair_caliber_mm,
        recommendation=analysis.recommendation.value.replace("_", " ").title(),
        confidence=analysis.confidence,
        reasoning=analysis.reasoning,
        match_score=match_score,
        zones_analyzed=zones_count,
        zone_breakdown=[ZoneBreakdown(
            zone_name=z.zone_name,
            density_score=z.density_score,
            estimated_grafts=z.estimated_grafts,
            coverage_area_cm2=z.coverage_area_cm2,
        ) for z in zone_breakdown],
    )


@router.post(
    "/with-simulation",
    summary="Analyze donor (multi-zone) + create simulation job",
    description="Analyze all donor zones and queue simulation if viable.",
)
@limiter.limit(_settings.rate_limit_generate)
async def analyze_and_simulate(
    request: Request,
    front_image: UploadFile = File(..., description="Frontal portrait"),
    coronilla_image: UploadFile = File(..., description="Back of head (coronilla)"),
    left_temporal_image: Optional[UploadFile] = File(None, description="Left side"),
    right_temporal_image: Optional[UploadFile] = File(None, description="Right side"),
    webhook_url: Optional[str] = Query(None),
    patient_reference: Optional[str] = Query(None),
):
    """
    Combined workflow: analyze all donor zones first, then queue simulation if viable.
    
    Returns:
    - Donor analysis immediately (with breakdown by zone)
    - Job ID for simulation (queued only if total donor supply is viable)
    """
    from app.deps import get_create_job_use_case
    from app.domain.job import DonorViability
    
    clinic_id = "default_clinic"
    
    # Read all images
    donor_images = {"coronilla": await coronilla_image.read()}
    if left_temporal_image:
        donor_images["left_temporal"] = await left_temporal_image.read()
    if right_temporal_image:
        donor_images["right_temporal"] = await right_temporal_image.read()
    
    front_bytes = await front_image.read()
    
    # Analyze all donor zones
    use_case = get_analyze_donor_use_case()
    result = await use_case.execute_multi_zone(
        clinic_id=clinic_id,
        donor_images=donor_images,
    )
    analysis = result["combined"]
    
    # Only queue simulation if viable
    job_id = None
    if analysis.recommendation in [
        DonorViability.VIABLE_SINGLE_SESSION,
        DonorViability.VIABLE_MULTIPLE_SESSIONS,
    ]:
        create_use_case = get_create_job_use_case()
        # Use coronilla as representative donor image for simulation
        job = await create_use_case.execute_single(
            clinic_id=clinic_id,
            front_image_bytes=front_bytes,
            donor_image_bytes=donor_images["coronilla"],
            webhook_url=webhook_url,
            patient_reference=patient_reference,
        )
        job_id = job.job_id
    
    return {
        "donor_analysis": {
            "density_score": analysis.density_score,
            "estimated_grafts": analysis.estimated_grafts,
            "zones_analyzed": result.zones_count,
            "recommendation": analysis.recommendation.value.replace("_", " ").title(),
            "confidence": analysis.confidence,
            "zone_breakdown": [
                {
                    "zone_name": z.zone_name,
                    "density_score": z.density_score,
                    "estimated_grafts": z.estimated_grafts,
                    "coverage_area_cm2": z.coverage_area_cm2,
                }
                for z in result.zone_breakdown
            ],
        },
        "simulation_job_id": job_id,
        "proceed_recommended": analysis.recommendation != DonorViability.NOT_RECOMMENDED,
    }
