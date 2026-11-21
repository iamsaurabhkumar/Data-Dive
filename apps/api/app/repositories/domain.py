"""
Plain domain objects for the planning bridge (ideas → Kanban → review).

Repositories translate these to/from storage; services and routers only
ever see these dataclasses.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Production pipeline shown as Kanban columns, in order.
PIPELINE = ("idea", "scripting", "filming", "editing", "published")
# "reviewed" is a terminal sub-state of Published (forecast compared with the real post);
# it is displayed inside the Published column, never as its own column.
STAGES = PIPELINE + ("reviewed",)
STAGE_LABELS = {
    "idea": "Ideas",
    "scripting": "Scripting",
    "filming": "Filming",
    "editing": "Editing",
    "published": "Published",
    "reviewed": "Reviewed",
}
LEGACY_STAGES = {"planning": "scripting", "production": "filming", "scheduled": "editing"}


def normalize_stage(stage: str) -> str:
    return LEGACY_STAGES.get(stage, stage)
IDEA_STATUSES = ("pending", "accepted", "rejected", "converted_to_kanban")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TransitionError(ValueError):
    pass


def validate_transition(from_stage: str, to_stage: str) -> None:
    to_stage = normalize_stage(to_stage)
    if to_stage not in STAGES:
        raise TransitionError(f"Unknown stage '{to_stage}'")
    if from_stage == "reviewed" and to_stage != "reviewed":
        raise TransitionError("A reviewed card is final; duplicate it to plan a follow-up.")
    if to_stage == "reviewed" and from_stage != "reviewed":
        raise TransitionError("Cards reach 'reviewed' through the review action, not by moving them.")


def next_slot_datetime(slot: Optional[Dict[str, Any]], after: Optional[datetime] = None) -> Optional[datetime]:
    """Next calendar datetime matching a recommended slot (weekday + hour bucket)."""
    if not slot or slot.get("weekday") is None:
        return None
    start_hour = {"morning": 9, "midday": 13, "evening": 18, "night": 22}.get(slot.get("hour_bucket", "morning"), 9)
    base = (after or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    days_ahead = (int(slot["weekday"]) - base.weekday()) % 7
    candidate = base.replace(hour=start_hour) + timedelta(days=days_ahead)
    if candidate <= base:
        candidate += timedelta(days=7)
    return candidate


@dataclass
class Card:
    creator_id: str
    title: str
    platform: str
    content_type: str
    id: str = field(default_factory=lambda: str(uuid4()))
    hook: str = ""
    outline: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    stage: str = "idea"
    position: int = 0
    suggestion_id: Optional[str] = None
    post_id: Optional[str] = None
    scheduled_for: Optional[str] = None
    published_at: Optional[str] = None
    prediction: Optional[Dict[str, Any]] = None
    recommended_slot: Optional[Dict[str, Any]] = None
    strategy: Optional[str] = None
    rationale: Optional[str] = None
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CardEvent:
    card_id: str
    from_stage: Optional[str]
    to_stage: str
    note: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Review:
    card_id: str
    creator_id: str
    post_id: Optional[str]
    result: Dict[str, Any]          # ReviewResult.to_dict()
    id: str = field(default_factory=lambda: str(uuid4()))
    reviewed_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(self.result)
        return d
