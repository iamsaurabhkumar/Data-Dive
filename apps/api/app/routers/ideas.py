"""Tailored content ideas (titles, hooks, outlines, predictions)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.core.redis import RedisUnavailableError, enqueue_task
from app.routers.deps import get_planning_service
from app.schemas.planning import CardSchema, GenerateIdeasRequest, IdeaSchema, IdeasListResponse
from app.services.planning import NotFound, PlanningService

router = APIRouter(prefix="/api/ideas", tags=["ideas"])
logger = logging.getLogger("datadive.ideas")


@router.get("", response_model=IdeasListResponse)
async def list_ideas(
    status: Optional[str] = Query("pending", description="pending | accepted | rejected | converted_to_kanban | all"),
    svc: PlanningService = Depends(get_planning_service),
):
    ideas = await svc.list_ideas(None if status in (None, "all") else status)
    return IdeasListResponse(ideas=[IdeaSchema(**i.to_dict()) for i in ideas], total=len(ideas))


@router.post("/generate", response_model=IdeasListResponse, status_code=201)
async def generate_ideas(
    body: GenerateIdeasRequest | None = None,
    svc: PlanningService = Depends(get_planning_service),
):
    body = body or GenerateIdeasRequest()
    ideas = await svc.generate_ideas(body.count, body.seed)
    if body.enrich and not get_settings().mock_mode:
        # Optional LLM polish runs in the worker; the forecast is never touched so it stays reviewable.
        for idea in ideas:
            try:
                await enqueue_task("enrich_idea", idea.id, _job_id=f"enrich:{idea.id}")
            except RedisUnavailableError as exc:
                logger.warning("Enrichment skipped (queue unavailable): %s", exc)
                break
    return IdeasListResponse(ideas=[IdeaSchema(**i.to_dict()) for i in ideas], total=len(ideas))


@router.get("/{idea_id}", response_model=IdeaSchema)
async def get_idea(idea_id: str, svc: PlanningService = Depends(get_planning_service)):
    """Single idea — used by the UI to poll for the worker's LLM enrichment."""
    try:
        return IdeaSchema(**(await svc.get_idea(idea_id)).to_dict())
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{idea_id}/to-board", response_model=CardSchema, status_code=201)
async def idea_to_board(idea_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        card = await svc.idea_to_board(idea_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return CardSchema(**svc._card_view(card))


@router.post("/{idea_id}/dismiss", response_model=IdeaSchema)
async def dismiss_idea(idea_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        idea = await svc.dismiss_idea(idea_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return IdeaSchema(**idea.to_dict())
