"""Usage tracking, preferences, feedback & survey endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.repositories.telemetry import SqlTelemetryRepository
from app.services.posts import ensure_creator_profile
from app.services.telemetry.models import InvalidEvent
from app.services.telemetry.service import TelemetryService, get_hub
from app.services.telemetry.taxonomy import FEATURES

router = APIRouter(tags=["telemetry"])


async def get_telemetry_service(
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
) -> TelemetryService:
    settings = get_settings()
    hub = get_hub()
    is_admin = user["sub"] in settings.admin_ids or (settings.mock_mode and not settings.admin_ids)
    if settings.mock_mode or db is None:
        return TelemetryService(hub.memory_repo(), hub, user["sub"], is_admin=is_admin)
    creator_id = await ensure_creator_profile(db, user["sub"])
    return TelemetryService(SqlTelemetryRepository(db), hub, creator_id, is_admin=is_admin)


# ---- schemas ---------------------------------------------------------------
class EventIn(BaseModel):
    name: str = "feature_used"
    feature: str
    action: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    page: Optional[str] = None
    session_id: Optional[str] = None
    duration_ms: Optional[int] = None
    ts: Optional[str] = None


class EventsBatch(BaseModel):
    events: List[EventIn] = Field(default_factory=list, max_length=100)


class PreferencesIn(BaseModel):
    telemetry_opt_out: bool


class FeedbackIn(BaseModel):
    feature: str
    rating: int = Field(..., ge=1, le=5)
    worth_it: str = Field(..., pattern="^(yes|somewhat|no)$")
    improvement: Optional[str] = Field("", max_length=1000)
    context: Optional[Dict[str, Any]] = None
    trigger: str = "manual"


# ---- telemetry -------------------------------------------------------------
@router.post("/api/telemetry/events", status_code=202)
async def ingest_events(batch: EventsBatch, svc: TelemetryService = Depends(get_telemetry_service)):
    """Batch ingestion from the browser SDK. Returns 202 immediately; storage/export is async."""
    return await svc.ingest([e.model_dump() for e in batch.events], client="web")


@router.get("/api/telemetry/features")
async def list_features():
    return {"features": [{"id": k, "label": v} for k, v in FEATURES.items()]}


@router.get("/api/telemetry/preferences")
async def get_preferences(svc: TelemetryService = Depends(get_telemetry_service)):
    return await svc.get_preferences()


@router.patch("/api/telemetry/preferences")
async def set_preferences(body: PreferencesIn, svc: TelemetryService = Depends(get_telemetry_service)):
    return await svc.set_preferences(body.telemetry_opt_out)


@router.get("/api/telemetry/summary")
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("me", pattern="^(me|all)$"),
    svc: TelemetryService = Depends(get_telemetry_service),
):
    if scope == "all" and not svc.is_admin:
        raise HTTPException(status_code=403, detail="scope=all requires an admin user (ADMIN_USER_IDS)")
    return await svc.summary(days, scope)


# ---- feedback --------------------------------------------------------------
@router.get("/api/feedback/prompt")
async def feedback_prompt(
    feature: str,
    moment: Optional[str] = Query(None, description="The action that just happened, e.g. review"),
    svc: TelemetryService = Depends(get_telemetry_service),
):
    """Should the UI show the micro-survey for this feature right now?"""
    return await svc.should_prompt(feature, moment)


@router.post("/api/feedback/prompt/{feature}/dismiss", status_code=204)
async def dismiss_prompt(feature: str, svc: TelemetryService = Depends(get_telemetry_service)):
    await svc.dismiss_prompt(feature)


@router.post("/api/feedback", status_code=201)
async def submit_feedback(body: FeedbackIn, svc: TelemetryService = Depends(get_telemetry_service)):
    try:
        fb = await svc.submit_feedback(body.model_dump())
    except InvalidEvent as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return fb.to_dict()


@router.get("/api/feedback/questions/{feature}")
async def feedback_questions(feature: str):
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail="unknown feature")
    return {"feature": feature, "label": FEATURES[feature], "questions": TelemetryService.questions(feature)}
