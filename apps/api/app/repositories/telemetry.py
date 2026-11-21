"""
Telemetry stores: in-memory (mock mode / tests) and SQL.

Both expose the same async interface; the service never branches on mode.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Protocol, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.creator import CreatorProfile
from app.models.telemetry import FeatureFeedbackRow, SurveyPromptRow, UsageEventRow
from app.services.telemetry.models import FeatureFeedback, SurveyPromptRecord, UsageEvent


class TelemetryRepository(Protocol):
    async def add_events(self, events: Sequence[UsageEvent]) -> int: ...
    async def list_events(self, creator_id: Optional[str], since: datetime) -> List[UsageEvent]: ...
    async def count_feature_uses(self, creator_id: str, feature: str, since: Optional[datetime] = None) -> int: ...
    async def add_feedback(self, fb: FeatureFeedback) -> FeatureFeedback: ...
    async def list_feedback(self, creator_id: Optional[str], since: datetime) -> List[FeatureFeedback]: ...
    async def last_feedback_at(self, creator_id: str, feature: str) -> Optional[datetime]: ...
    async def add_prompt(self, rec: SurveyPromptRecord) -> SurveyPromptRecord: ...
    async def mark_dismissed(self, creator_id: str, feature: str, at: Optional[datetime] = None) -> None: ...
    async def prompts(self, creator_id: str, since: datetime) -> List[SurveyPromptRecord]: ...
    async def is_opted_out(self, creator_id: str) -> bool: ...
    async def set_opt_out(self, creator_id: str, opt_out: bool) -> None: ...


# ---------------------------------------------------------------------------
class MemoryTelemetryRepository:
    def __init__(self) -> None:
        self.events: List[UsageEvent] = []
        self.feedback: List[FeatureFeedback] = []
        self.prompt_records: List[SurveyPromptRecord] = []
        self.opt_outs: set = set()

    async def add_events(self, events: Sequence[UsageEvent]) -> int:
        self.events.extend(events)
        return len(events)

    async def list_events(self, creator_id: Optional[str], since: datetime) -> List[UsageEvent]:
        return [e for e in self.events if e.ts >= since and (creator_id is None or e.creator_id == creator_id)]

    async def count_feature_uses(self, creator_id: str, feature: str, since: Optional[datetime] = None) -> int:
        return sum(1 for e in self.events if e.creator_id == creator_id and e.feature == feature
                   and e.name in ("feature_used", "api_call") and (since is None or e.ts >= since))

    async def add_feedback(self, fb: FeatureFeedback) -> FeatureFeedback:
        self.feedback.append(fb)
        return fb

    async def list_feedback(self, creator_id: Optional[str], since: datetime) -> List[FeatureFeedback]:
        return [f for f in self.feedback if f.created_at >= since and (creator_id is None or f.creator_id == creator_id)]

    async def last_feedback_at(self, creator_id: str, feature: str) -> Optional[datetime]:
        ts = [f.created_at for f in self.feedback if f.creator_id == creator_id and f.feature == feature]
        return max(ts) if ts else None

    async def add_prompt(self, rec: SurveyPromptRecord) -> SurveyPromptRecord:
        self.prompt_records.append(rec)
        return rec

    async def mark_dismissed(self, creator_id: str, feature: str, at: Optional[datetime] = None) -> None:
        for r in reversed(self.prompt_records):
            if r.creator_id == creator_id and r.feature == feature:
                r.dismissed = True
                return
        rec = SurveyPromptRecord(creator_id=creator_id, feature=feature, dismissed=True)
        if at is not None:
            rec.created_at = at
        self.prompt_records.append(rec)

    async def prompts(self, creator_id: str, since: datetime) -> List[SurveyPromptRecord]:
        return [r for r in self.prompt_records if r.creator_id == creator_id and r.created_at >= since]

    async def is_opted_out(self, creator_id: str) -> bool:
        return creator_id in self.opt_outs

    async def set_opt_out(self, creator_id: str, opt_out: bool) -> None:
        (self.opt_outs.add if opt_out else self.opt_outs.discard)(creator_id)


# ---------------------------------------------------------------------------
def _uuid(v: Optional[str]) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None


def _event_from_row(r: UsageEventRow) -> UsageEvent:
    return UsageEvent(
        id=str(r.id), name=r.name, feature=r.feature, creator_id=str(r.creator_id) if r.creator_id else None,
        action=r.action, properties=dict(r.properties or {}), page=r.page, session_id=r.session_id,
        client=r.client, duration_ms=r.duration_ms, status=r.status, ts=r.ts,
    )


def _feedback_from_row(r: FeatureFeedbackRow) -> FeatureFeedback:
    return FeatureFeedback(
        id=str(r.id), creator_id=str(r.creator_id), feature=r.feature, rating=r.rating, worth_it=r.worth_it,
        improvement=r.improvement or "", context=dict(r.context or {}), trigger=r.trigger, created_at=r.created_at,
    )


class SqlTelemetryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_events(self, events: Sequence[UsageEvent]) -> int:
        # Events may arrive before the creator profile row exists (first request of a new
        # user) — keep the event, drop the FK reference instead of failing the whole batch.
        wanted = {_uuid(e.creator_id) for e in events if e.creator_id}
        wanted.discard(None)
        known = set()
        if wanted:
            rows = (await self.db.execute(select(CreatorProfile.id).where(CreatorProfile.id.in_(wanted)))).all()
            known = {r[0] for r in rows}
        for e in events:
            cid = _uuid(e.creator_id)
            self.db.add(UsageEventRow(
                id=_uuid(e.id), creator_id=cid if cid in known else None, session_id=e.session_id, name=e.name,
                feature=e.feature, action=e.action, properties=e.properties, page=e.page, client=e.client,
                duration_ms=e.duration_ms, status=e.status, ts=e.ts,
            ))
        await self.db.flush()
        return len(events)

    async def list_events(self, creator_id: Optional[str], since: datetime) -> List[UsageEvent]:
        stmt = select(UsageEventRow).where(UsageEventRow.ts >= since)
        if creator_id is not None:
            stmt = stmt.where(UsageEventRow.creator_id == _uuid(creator_id))
        rows = (await self.db.execute(stmt.order_by(UsageEventRow.ts))).scalars().all()
        return [_event_from_row(r) for r in rows]

    async def count_feature_uses(self, creator_id: str, feature: str, since: Optional[datetime] = None) -> int:
        stmt = select(func.count()).select_from(UsageEventRow).where(
            UsageEventRow.creator_id == _uuid(creator_id), UsageEventRow.feature == feature,
            UsageEventRow.name.in_(("feature_used", "api_call")),
        )
        if since is not None:
            stmt = stmt.where(UsageEventRow.ts >= since)
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def add_feedback(self, fb: FeatureFeedback) -> FeatureFeedback:
        self.db.add(FeatureFeedbackRow(
            id=_uuid(fb.id), creator_id=_uuid(fb.creator_id), feature=fb.feature, rating=fb.rating,
            worth_it=fb.worth_it, improvement=fb.improvement, context=fb.context, trigger=fb.trigger,
        ))
        await self.db.flush()
        return fb

    async def list_feedback(self, creator_id: Optional[str], since: datetime) -> List[FeatureFeedback]:
        stmt = select(FeatureFeedbackRow).where(FeatureFeedbackRow.created_at >= since)
        if creator_id is not None:
            stmt = stmt.where(FeatureFeedbackRow.creator_id == _uuid(creator_id))
        rows = (await self.db.execute(stmt.order_by(FeatureFeedbackRow.created_at))).scalars().all()
        return [_feedback_from_row(r) for r in rows]

    async def last_feedback_at(self, creator_id: str, feature: str) -> Optional[datetime]:
        stmt = select(func.max(FeatureFeedbackRow.created_at)).where(
            FeatureFeedbackRow.creator_id == _uuid(creator_id), FeatureFeedbackRow.feature == feature)
        return (await self.db.execute(stmt)).scalar()

    async def add_prompt(self, rec: SurveyPromptRecord) -> SurveyPromptRecord:
        self.db.add(SurveyPromptRow(id=_uuid(rec.id), creator_id=_uuid(rec.creator_id), feature=rec.feature,
                                    dismissed=rec.dismissed, created_at=rec.created_at))
        await self.db.flush()
        return rec

    async def mark_dismissed(self, creator_id: str, feature: str, at: Optional[datetime] = None) -> None:
        stmt = select(SurveyPromptRow).where(
            SurveyPromptRow.creator_id == _uuid(creator_id), SurveyPromptRow.feature == feature
        ).order_by(SurveyPromptRow.created_at.desc()).limit(1)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = SurveyPromptRow(creator_id=_uuid(creator_id), feature=feature, created_at=at or datetime.now(timezone.utc))
            self.db.add(row)
        row.dismissed = True
        await self.db.flush()

    async def prompts(self, creator_id: str, since: datetime) -> List[SurveyPromptRecord]:
        stmt = select(SurveyPromptRow).where(SurveyPromptRow.creator_id == _uuid(creator_id), SurveyPromptRow.created_at >= since)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [SurveyPromptRecord(id=str(r.id), creator_id=str(r.creator_id), feature=r.feature,
                                   dismissed=bool(r.dismissed), created_at=r.created_at) for r in rows]

    async def is_opted_out(self, creator_id: str) -> bool:
        row = await self.db.get(CreatorProfile, _uuid(creator_id))
        return bool(row and row.telemetry_opt_out)

    async def set_opt_out(self, creator_id: str, opt_out: bool) -> None:
        row = await self.db.get(CreatorProfile, _uuid(creator_id))
        if row is not None:
            row.telemetry_opt_out = opt_out
            await self.db.flush()
