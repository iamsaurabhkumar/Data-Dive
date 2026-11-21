"""Cross-platform analytics: overview, patterns, learning."""
from fastapi import APIRouter, Depends

from app.routers.deps import get_planning_service
from app.schemas.planning import LearningResponse, OverviewResponse, PatternsResponse
from app.services.planning import PlanningService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewResponse)
async def analytics_overview(svc: PlanningService = Depends(get_planning_service)):
    """Normalized YouTube vs Instagram comparison (views, engagement, momentum, cadence, best format)."""
    return svc.overview()


@router.get("/patterns", response_model=PatternsResponse)
async def analytics_patterns(svc: PlanningService = Depends(get_planning_service)):
    """Topic, format and posting-time patterns with confidence + plain-language findings."""
    return svc.patterns()


@router.get("/learning", response_model=LearningResponse)
async def analytics_learning(svc: PlanningService = Depends(get_planning_service)):
    """How accurate past predictions were and the calibration the system has learned."""
    return await svc.learning()
