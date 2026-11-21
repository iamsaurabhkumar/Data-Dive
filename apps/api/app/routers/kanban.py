"""Kanban production board: cards, stage transitions, post linking and prediction reviews."""
from fastapi import APIRouter, Depends, HTTPException, Response

from app.repositories.domain import TransitionError
from app.routers.deps import get_planning_service
from app.schemas.planning import (
    BoardResponse,
    CardCreateRequest,
    CardMoveRequest,
    CardSchema,
    CardUpdateRequest,
    LinkPostRequest,
    ReviewRequest,
)
from app.services.planning import NotFound, PlanningService

router = APIRouter(prefix="/api/kanban", tags=["kanban"])


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


@router.get("/board", response_model=BoardResponse)
async def get_board(svc: PlanningService = Depends(get_planning_service)):
    return await svc.board()


@router.post("/cards", response_model=CardSchema, status_code=201)
async def create_card(body: CardCreateRequest, svc: PlanningService = Depends(get_planning_service)):
    try:
        card = await svc.create_card(body.model_dump())
    except (NotFound, TransitionError) as exc:
        raise _handle(exc)
    return CardSchema(**svc._card_view(card))


@router.get("/cards/{card_id}", response_model=CardSchema)
async def get_card(card_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        return await svc.card_detail(card_id)
    except NotFound as exc:
        raise _handle(exc)


@router.patch("/cards/{card_id}", response_model=CardSchema)
async def update_card(card_id: str, body: CardUpdateRequest, svc: PlanningService = Depends(get_planning_service)):
    try:
        card = await svc.update_card(card_id, body.model_dump(exclude_unset=True))
    except NotFound as exc:
        raise _handle(exc)
    return CardSchema(**svc._card_view(card))


@router.post("/cards/{card_id}/move", response_model=CardSchema)
async def move_card(card_id: str, body: CardMoveRequest, svc: PlanningService = Depends(get_planning_service)):
    try:
        card = await svc.move_card(card_id, body.stage, body.position, body.note)
    except (NotFound, TransitionError) as exc:
        raise _handle(exc)
    return CardSchema(**svc._card_view(card))


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(card_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        await svc.delete_card(card_id)
    except NotFound as exc:
        raise _handle(exc)
    return Response(status_code=204)


@router.get("/cards/{card_id}/events")
async def card_events(card_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        return {"events": await svc.events(card_id)}
    except NotFound as exc:
        raise _handle(exc)


@router.post("/cards/{card_id}/link-post", response_model=CardSchema)
async def link_post(card_id: str, body: LinkPostRequest, svc: PlanningService = Depends(get_planning_service)):
    try:
        card = await svc.link_post(card_id, body.post_id, body.auto)
    except (NotFound, TransitionError) as exc:
        raise _handle(exc)
    return CardSchema(**svc._card_view(card))


@router.post("/cards/{card_id}/review", response_model=CardSchema)
async def review_card(card_id: str, body: ReviewRequest | None = None,
                      svc: PlanningService = Depends(get_planning_service)):
    body = body or ReviewRequest()
    try:
        return await svc.review_card(card_id, body.min_age_days)
    except (NotFound, TransitionError) as exc:
        raise _handle(exc)


@router.get("/cards/{card_id}/review")
async def get_review(card_id: str, svc: PlanningService = Depends(get_planning_service)):
    try:
        return await svc.get_review(card_id)
    except NotFound as exc:
        raise _handle(exc)
