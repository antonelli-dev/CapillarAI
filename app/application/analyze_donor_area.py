"""Use case: Analyze donor area viability (CPU-only)."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from app.domain.report import DonorAnalysis
from app.ports.donor_analyzer import DonorAnalyzerPort
from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


@dataclass
class ZoneResult:
    """Result for a single donor zone."""
    zone_name: str
    density_score: float
    estimated_grafts: int
    coverage_area_cm2: float


@dataclass
class MultiZoneAnalysisResult:
    """Combined result from multiple donor zones."""
    combined: DonorAnalysis
    zone_breakdown: List[ZoneResult]
    zones_count: int


class AnalyzeDonorAreaUseCase:
    """
    Quick donor area analysis without full simulation.
    Returns density score, graft estimate, and viability recommendation.
    """
    
    def __init__(
        self,
        donor_analyzer: DonorAnalyzerPort,
        storage: StoragePort,
    ):
        self.donor_analyzer = donor_analyzer
        self.storage = storage
    
    async def execute(
        self,
        clinic_id: str,
        donor_image_bytes: bytes,
        recipient_area_cm2: Optional[float] = None,
    ) -> DonorAnalysis:
        """
        Analyze donor area and calculate match with recipient needs.
        
        Args:
            clinic_id: Organization ID
            donor_image_bytes: Image of donor area (coronilla/posterior)
            recipient_area_cm2: Optional recipient area for coverage calculation
            
        Returns:
            DonorAnalysis with density, grafts, recommendation
        """
        import cv2
        
        # Convert bytes to CV2
        nparr = np.frombuffer(donor_image_bytes, np.uint8)
        donor_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if donor_image is None:
            raise ValueError("Could not decode donor image")
        
        # Run analysis (CPU-only, fast)
        analysis = self.donor_analyzer.analyze(donor_image, recipient_area_cm2)
        
        # Calculate match score if recipient area provided
        if recipient_area_cm2 and recipient_area_cm2 > 0:
            match_score = self.donor_analyzer.calculate_match_score(
                analysis,
                recipient_area_cm2,
            )
            # Update reasoning based on match
            if match_score < 0.5:
                analysis.reasoning = (
                    f"Insufficient donor supply. "
                    f"Required: ~{int(recipient_area_cm2 * 25)} grafts, "
                    f"Available: ~{analysis.estimated_grafts} grafts"
                )
            else:
                analysis.reasoning = (
                    f"Donor area adequate. "
                    f"Coverage ratio: {match_score:.0%}"
                )
        
        return analysis
    
    async def execute_with_storage(
        self,
        clinic_id: str,
        donor_image_key: str,
        recipient_area_cm2: Optional[float] = None,
    ) -> DonorAnalysis:
        """Analyze from stored image (already uploaded)."""
        donor_bytes = await asyncio.to_thread(
            self.storage.download,
            donor_image_key,
        )
        return await self.execute(clinic_id, donor_bytes, recipient_area_cm2)
    
    async def execute_multi_zone(
        self,
        clinic_id: str,
        donor_images: dict,  # {"coronilla": bytes, "left_temporal": bytes, ...}
        recipient_area_cm2: Optional[float] = None,
    ) -> MultiZoneAnalysisResult:
        """
        Analyze multiple donor zones (coronilla + laterals) and sum results.
        
        Args:
            clinic_id: Organization ID
            donor_images: Dict with zone name -> image bytes
                         Required: "coronilla"
                         Optional: "left_temporal", "right_temporal"
            recipient_area_cm2: Optional recipient area for coverage calculation
            
        Returns:
            Combined DonorAnalysis with summed grafts from all zones
        """
        import cv2
        from typing import Dict, List
        
        if "coronilla" not in donor_images:
            raise ValueError("Coronilla image is required")
        
        # Analyze each zone
        zone_analyses: Dict[str, DonorAnalysis] = {}
        
        for zone_name, image_bytes in donor_images.items():
            # Convert bytes to CV2
            nparr = np.frombuffer(image_bytes, np.uint8)
            zone_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if zone_image is None:
                logger.warning(f"Could not decode {zone_name} image, skipping")
                continue
            
            # Analyze this zone
            analysis = self.donor_analyzer.analyze(zone_image)
            zone_analyses[zone_name] = analysis
            logger.info(f"{zone_name}: {analysis.estimated_grafts} grafts, density {analysis.density_score:.1f}")
        
        if not zone_analyses:
            raise ValueError("No valid donor images could be analyzed")
        
        # Combine results - sum grafts, average density
        total_grafts = sum(a.estimated_grafts for a in zone_analyses.values())
        avg_density = sum(a.density_score for a in zone_analyses.values()) / len(zone_analyses)
        total_coverage = sum(a.coverage_area_cm2 for a in zone_analyses.values())
        
        # Re-evaluate recommendation based on total
        from app.domain.report import DonorViability
        
        if avg_density < 3.0:
            recommendation = DonorViability.NOT_RECOMMENDED
            reasoning = f"Insufficient donor supply across {len(zone_analyses)} zones. Total: ~{total_grafts} grafts"
        elif avg_density < 5.0:
            recommendation = DonorViability.VIABLE_MULTIPLE_SESSIONS
            reasoning = f"Adequate donor supply. Total: ~{total_grafts} grafts from {len(zone_analyses)} zones"
        else:
            recommendation = DonorViability.VIABLE_SINGLE_SESSION
            reasoning = f"Excellent donor supply. Total: ~{total_grafts} grafts from {len(zone_analyses)} zones"
        
        # Calculate match score if recipient area provided
        confidence = 0.0
        if recipient_area_cm2 and recipient_area_cm2 > 0:
            # Create temporary object for match calculation
            temp_analysis = DonorAnalysis(
                density_score=avg_density,
                estimated_grafts=total_grafts,
                coverage_area_cm2=total_coverage,
                recommendation=recommendation,
            )
            match_score = self.donor_analyzer.calculate_match_score(
                temp_analysis,
                recipient_area_cm2,
            )
            confidence = min(0.95, match_score + 0.1)
            
            if match_score < 0.5:
                reasoning += f". WARNING: Insufficient for recipient area ({match_score:.0%} coverage)"
            else:
                reasoning += f". Good match: {match_score:.0%} coverage"
        
        # Create new combined analysis (DonorAnalysis is frozen)
        coronilla = zone_analyses["coronilla"]
        combined = DonorAnalysis(
            density_score=avg_density,
            estimated_grafts=total_grafts,
            coverage_area_cm2=total_coverage,
            hair_caliber_mm=coronilla.hair_caliber_mm,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
        )
        
        # Return combined analysis + zone breakdown
        zone_results = [
            ZoneResult(
                zone_name=name,
                density_score=a.density_score,
                estimated_grafts=a.estimated_grafts,
                coverage_area_cm2=a.coverage_area_cm2,
            )
            for name, a in zone_analyses.items()
        ]
        
        return MultiZoneAnalysisResult(
            combined=combined,
            zone_breakdown=zone_results,
            zones_count=len(zone_analyses),
        )
