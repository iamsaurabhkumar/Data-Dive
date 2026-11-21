"""
"Generate Next Project" — one click on the Insights page.

The API answers immediately with a complete, trend-driven project built by the
analytics engine; the optional LLM polish (title/hook/outline in the creator's
voice) runs in the worker, and the UI polls GET /api/ideas/{id} for it.
Heavy external calls never happen in the request path (V2 spec).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.redis import RedisUnavailableError, enqueue_task
from app.db.session import get_db
from app.routers.deps import get_planning_service
from app.schemas.planning import IdeaSchema, NextProjectRequest, NextProjectResponse, ScoredTrendSchema
from app.services.planning import PlanningService
from app.services.trends import load_trends

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger("datadive.projects")


@router.post("/next", response_model=NextProjectResponse, status_code=201)
async def generate_next_project(
    body: Optional[NextProjectRequest] = None,
    svc: PlanningService = Depends(get_planning_service),
    db: Optional[AsyncSession] = Depends(get_db),
):
    body = body or NextProjectRequest()
    settings = get_settings()
    trends = await load_trends(db)

    can_enrich = body.enrich and settings.ai_enrichment_enabled and not settings.mock_mode
    result = await svc.next_project(trends, body.exclude_trend_ids, body.platform,
                                    enrichment_status="queued" if can_enrich else None)
    idea = result.idea

    enrichment = "disabled"
    if can_enrich:
        try:
            job = await enqueue_task("enrich_idea", idea.id, _job_id=f"enrich:{idea.id}")
            enrichment = "queued" if job else "unavailable"
        except (RedisUnavailableError, Exception) as exc:  # queue down must never fail the click
            logger.warning("LLM enrichment not queued: %s", exc)
            enrichment = "unavailable"
        if enrichment != "queued":
            idea.enrichment_status = None
            await svc.set_enrichment_status(idea.id, None)

    trend_refresh = None
    if result.fallback_reason == "no_trends" and not settings.mock_mode:
        try:
            hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
            await enqueue_task("fetch_and_analyze_trends", svc.creator_id, "youtube", _job_id=f"trends:{svc.creator_id}:{hour}")
            trend_refresh = "queued"
        except Exception as exc:
            logger.warning("Trend refresh not queued: %s", exc)

    return NextProjectResponse(
        idea=IdeaSchema(**idea.to_dict()),
        trend=ScoredTrendSchema(**result.chosen.to_dict()) if result.chosen else None,
        alternatives=[ScoredTrendSchema(**s.to_dict()) for s in result.alternatives],
        trends_considered=result.trends_considered,
        fallback_reason=result.fallback_reason,
        enrichment=enrichment,
        trend_refresh=trend_refresh,
    )
