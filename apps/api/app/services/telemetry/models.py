"""Domain objects for usage events and feedback."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.services.telemetry.taxonomy import EVENT_NAMES, FEATURES

MAX_PROPERTIES_BYTES = 2048
MAX_ACTION_LEN = 64
CLOCK_SKEW = timedelta(minutes=5)


class InvalidEvent(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_properties(props: Any) -> Dict[str, Any]:
    """Only flat JSON scalars (and short lists of scalars). Never free text blobs."""
    if not props:
        return {}
    if not isinstance(props, dict):
        raise InvalidEvent("properties must be an object")
    out: Dict[str, Any] = {}
    for k, v in props.items():
        if not isinstance(k, str) or len(k) > 48:
            continue
        if isinstance(v, (bool, int, float)) or v is None:
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:120]
        elif isinstance(v, list) and len(v) <= 10 and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = [x[:60] if isinstance(x, str) else x for x in v]
    if len(json.dumps(out)) > MAX_PROPERTIES_BYTES:
        raise InvalidEvent("properties too large")
    return out


def clamp_timestamp(ts: Any, server_now: Optional[datetime] = None) -> datetime:
    server_now = server_now or now_utc()
    if ts is None or ts == "":
        return server_now
    if isinstance(ts, datetime):
        dt = ts
    else:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return server_now
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if dt > server_now + CLOCK_SKEW:
        return server_now
    if dt < server_now - timedelta(days=2):
        return server_now - timedelta(days=2)
    return dt


@dataclass
class UsageEvent:
    name: str
    feature: str
    creator_id: Optional[str]
    action: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    page: Optional[str] = None
    session_id: Optional[str] = None
    client: str = "web"
    duration_ms: Optional[int] = None
    status: Optional[int] = None
    ts: datetime = field(default_factory=now_utc)
    id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def build(cls, creator_id: Optional[str], data: Dict[str, Any], client: str = "web",
              server_now: Optional[datetime] = None) -> "UsageEvent":
        name = str(data.get("name") or "feature_used")
        if name not in EVENT_NAMES:
            raise InvalidEvent(f"unknown event name '{name}'")
        feature = str(data.get("feature") or "other").lower()
        if feature not in FEATURES:
            feature = "other"
        action = data.get("action")
        if action is not None:
            action = str(action).lower().strip()[:MAX_ACTION_LEN] or None
        page = data.get("page")
        if page is not None:
            page = str(page).split("?", 1)[0][:120]
        duration = data.get("duration_ms")
        duration = int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None
        status = data.get("status")
        status = int(status) if isinstance(status, int) else None
        session_id = data.get("session_id")
        session_id = str(session_id)[:64] if session_id else None
        return cls(
            name=name, feature=feature, creator_id=creator_id, action=action,
            properties=sanitize_properties(data.get("properties")), page=page,
            session_id=session_id, client=client, duration_ms=duration, status=status,
            ts=clamp_timestamp(data.get("ts"), server_now),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d

    def export(self, salt: str) -> Dict[str, Any]:
        """Anonymized representation for external sinks."""
        d = self.to_dict()
        d["creator_hash"] = hash_creator(self.creator_id, salt)
        d.pop("creator_id", None)
        d["type"] = "usage_event"
        d["source"] = "data-dive"
        return d


def hash_creator(creator_id: Optional[str], salt: str) -> Optional[str]:
    if not creator_id:
        return None
    return hashlib.sha256(f"{salt}:{creator_id}".encode()).hexdigest()[:32]


WORTH_VALUES = ("yes", "somewhat", "no")


@dataclass
class FeatureFeedback:
    creator_id: str
    feature: str
    rating: int                         # 1..5
    worth_it: str                       # yes | somewhat | no
    improvement: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    trigger: str = "manual"             # manual | prompt
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)

    def validate(self) -> None:
        if self.feature not in FEATURES:
            raise InvalidEvent(f"unknown feature '{self.feature}'")
        if not 1 <= int(self.rating) <= 5:
            raise InvalidEvent("rating must be between 1 and 5")
        if self.worth_it not in WORTH_VALUES:
            raise InvalidEvent("worth_it must be yes | somewhat | no")
        self.improvement = (self.improvement or "").strip()[:1000]
        self.context = sanitize_properties(self.context)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d


@dataclass
class SurveyPromptRecord:
    """A prompt that was shown (and maybe dismissed) — used for frequency capping."""
    creator_id: str
    feature: str
    dismissed: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
