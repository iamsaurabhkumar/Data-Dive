"""
TelemetryHub — the process-wide ingestion buffer + flusher, and the
per-request TelemetryService (feedback/prompt/summary logic).

Ingestion path (both middleware and /api/telemetry/events):
    record(event) → opt-out check (cached) → buffer → flush()
        flush → repository (db sink) + external sinks with anonymized payloads
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.config import Settings, get_settings
from app.repositories.telemetry import MemoryTelemetryRepository, SqlTelemetryRepository, TelemetryRepository
from app.services.telemetry.models import FeatureFeedback, InvalidEvent, SurveyPromptRecord, UsageEvent, now_utc
from app.services.telemetry.sinks import Sink, build_sinks
from app.services.telemetry.summary import summarize
from app.services.telemetry.taxonomy import FEATURES, FEEDBACK_MOMENTS

logger = logging.getLogger("datadive.telemetry")

OPT_OUT_CACHE_TTL = 60.0


class TelemetryHub:
    """One per process. Owns the buffer, the sinks and the background flush loop."""

    def __init__(self, settings: Optional[Settings] = None, sinks: Optional[List[Sink]] = None):
        self.settings = settings or get_settings()
        self.sinks: List[Sink] = sinks if sinks is not None else build_sinks(self.settings)
        self.store_in_db = "db" in self.settings.telemetry_sink_list
        self._buffer: List[UsageEvent] = []
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._memory_repo: Optional[MemoryTelemetryRepository] = None
        self._opt_out_cache: Dict[str, tuple[bool, float]] = {}
        self.stats = {"recorded": 0, "dropped_opt_out": 0, "flushed": 0, "sink_errors": 0}

    # ---- repositories ------------------------------------------------------
    def memory_repo(self) -> MemoryTelemetryRepository:
        if self._memory_repo is None:
            self._memory_repo = MemoryTelemetryRepository()
        return self._memory_repo

    def _session_factory(self):
        from app.db.session import get_session_factory
        return get_session_factory()

    async def _with_repo(self, fn: Callable[[TelemetryRepository], Any]) -> Any:
        """Run fn against the right repository, committing if it is SQL-backed."""
        if self.settings.mock_mode:
            return await fn(self.memory_repo())
        async with self._session_factory()() as session:
            result = await fn(SqlTelemetryRepository(session))
            await session.commit()
            return result

    # ---- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._task is None and self.settings.telemetry_enabled:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        await self.flush()
        for s in self.sinks:
            try:
                await s.close()
            except Exception:
                logger.exception("Error closing sink %s", s.name)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.telemetry_flush_seconds)
            try:
                await self.flush()
            except Exception:
                logger.exception("Telemetry flush failed")

    # ---- ingestion ---------------------------------------------------------
    async def is_opted_out(self, creator_id: Optional[str]) -> bool:
        if not creator_id:
            return False
        cached = self._opt_out_cache.get(creator_id)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        try:
            value = await self._with_repo(lambda r: r.is_opted_out(creator_id))
        except Exception:
            logger.exception("Opt-out lookup failed; assuming opted in")
            value = False
        self._opt_out_cache[creator_id] = (value, time.monotonic() + OPT_OUT_CACHE_TTL)
        return value

    def invalidate_opt_out(self, creator_id: str) -> None:
        self._opt_out_cache.pop(creator_id, None)

    async def record(self, event: UsageEvent) -> bool:
        if not self.settings.telemetry_enabled:
            return False
        if await self.is_opted_out(event.creator_id):
            self.stats["dropped_opt_out"] += 1
            return False
        async with self._lock:
            self._buffer.append(event)
            self.stats["recorded"] += 1
            full = len(self._buffer) >= self.settings.telemetry_max_buffer
        if full:
            await self.flush()
        return True

    async def record_many(self, events: Sequence[UsageEvent]) -> int:
        n = 0
        for e in events:
            if await self.record(e):
                n += 1
        return n

    async def flush(self) -> int:
        async with self._lock:
            batch, self._buffer = self._buffer, []
        if not batch:
            return 0
        if self.store_in_db:
            try:
                await self._with_repo(lambda r: r.add_events(batch))
            except Exception:
                logger.exception("Failed to persist %d usage events", len(batch))
        if self.sinks:
            payload = [e.export(self.settings.telemetry_hash_salt) for e in batch]
            for sink in self.sinks:
                try:
                    await sink.emit(payload)
                except Exception:
                    self.stats["sink_errors"] += 1
                    logger.exception("Telemetry sink %s failed for %d events", sink.name, len(payload))
        self.stats["flushed"] += len(batch)
        return len(batch)


_hub: Optional[TelemetryHub] = None


def get_hub() -> TelemetryHub:
    global _hub
    if _hub is None:
        _hub = TelemetryHub()
    return _hub


def reset_hub() -> None:
    """Test helper."""
    global _hub
    _hub = None


# ---------------------------------------------------------------------------
class TelemetryService:
    """Per-request operations: feedback, survey prompting, summaries, preferences."""

    def __init__(self, repo: TelemetryRepository, hub: TelemetryHub, creator_id: str, is_admin: bool = False,
                 settings: Optional[Settings] = None, now: Optional[datetime] = None):
        self.repo = repo
        self.hub = hub
        self.creator_id = creator_id
        self.is_admin = is_admin
        self.settings = settings or get_settings()
        self.now = now or now_utc()

    # ---- events -----------------------------------------------------------
    async def ingest(self, raw_events: Sequence[Dict[str, Any]], client: str = "web") -> Dict[str, int]:
        accepted: List[UsageEvent] = []
        rejected = 0
        for raw in raw_events[:100]:
            try:
                accepted.append(UsageEvent.build(self.creator_id, raw, client=client, server_now=self.now))
            except (InvalidEvent, TypeError, ValueError):
                rejected += 1
        stored = await self.hub.record_many(accepted)
        return {"accepted": stored, "rejected": rejected, "dropped": len(accepted) - stored}

    # ---- preferences ------------------------------------------------------
    async def get_preferences(self) -> Dict[str, Any]:
        return {"telemetry_opt_out": await self.repo.is_opted_out(self.creator_id),
                "sinks": [s.name for s in self.hub.sinks] + (["db"] if self.hub.store_in_db else [])}

    async def set_preferences(self, opt_out: bool) -> Dict[str, Any]:
        await self.repo.set_opt_out(self.creator_id, opt_out)
        self.hub.invalidate_opt_out(self.creator_id)
        return await self.get_preferences()

    # ---- feedback ---------------------------------------------------------
    async def should_prompt(self, feature: str, moment: Optional[str] = None) -> Dict[str, Any]:
        if feature not in FEATURES:
            return {"prompt": False, "reason": "unknown_feature", "feature": feature}
        if moment and moment not in FEEDBACK_MOMENTS.get(feature, (moment,)):
            return {"prompt": False, "reason": "not_a_feedback_moment", "feature": feature}
        s = self.settings
        await self.hub.flush()  # count what just happened, not what was flushed 5 s ago
        uses = await self.repo.count_feature_uses(self.creator_id, feature)
        if uses < s.feedback_min_uses:
            return {"prompt": False, "reason": "too_few_uses", "feature": feature, "uses": uses, "needed": s.feedback_min_uses}
        last = await self.repo.last_feedback_at(self.creator_id, feature)
        if last and last >= self.now - timedelta(days=s.feedback_cooldown_days):
            return {"prompt": False, "reason": "recent_feedback", "feature": feature, "uses": uses}
        recent = await self.repo.prompts(self.creator_id, self.now - timedelta(days=s.feedback_dismiss_cooldown_days))
        if any(p.feature == feature and p.dismissed for p in recent):
            return {"prompt": False, "reason": "recently_dismissed", "feature": feature, "uses": uses}
        today = [p for p in recent if p.created_at >= self.now - timedelta(days=1)]
        if len(today) >= s.feedback_max_prompts_per_day:
            return {"prompt": False, "reason": "daily_cap", "feature": feature, "uses": uses}
        await self.repo.add_prompt(SurveyPromptRecord(creator_id=self.creator_id, feature=feature, created_at=self.now))
        await self.hub.record(UsageEvent(name="survey_shown", feature=feature, creator_id=self.creator_id,
                                         action=moment, client="api", ts=self.now))
        return {"prompt": True, "reason": "eligible", "feature": feature, "uses": uses,
                "questions": self.questions(feature)}

    @staticmethod
    def questions(feature: str) -> List[Dict[str, Any]]:
        label = FEATURES.get(feature, feature)
        return [
            {"id": "rating", "type": "scale", "min": 1, "max": 5, "text": f"How would you rate {label}?"},
            {"id": "worth_it", "type": "choice", "options": ["yes", "somewhat", "no"], "text": "Was it worth using?"},
            {"id": "improvement", "type": "text", "max_length": 1000, "optional": True,
             "text": "What should we improve or add?"},
        ]

    async def dismiss_prompt(self, feature: str) -> None:
        await self.repo.mark_dismissed(self.creator_id, feature, at=self.now)
        await self.hub.record(UsageEvent(name="survey_dismissed", feature=feature, creator_id=self.creator_id,
                                         client="api", ts=self.now))

    async def submit_feedback(self, data: Dict[str, Any]) -> FeatureFeedback:
        fb = FeatureFeedback(
            creator_id=self.creator_id,
            feature=str(data.get("feature") or "other").lower(),
            rating=int(data.get("rating") or 0),
            worth_it=str(data.get("worth_it") or "").lower(),
            improvement=str(data.get("improvement") or ""),
            context=data.get("context") or {},
            trigger="prompt" if data.get("trigger") == "prompt" else "manual",
            created_at=self.now,
        )
        fb.validate()
        await self.repo.add_feedback(fb)
        # Sentiment travels with the usage stream — never the free text.
        await self.hub.record(UsageEvent(
            name="feedback_submitted", feature=fb.feature, creator_id=self.creator_id, action=fb.trigger,
            properties={"rating": fb.rating, "worth_it": fb.worth_it, "has_comment": bool(fb.improvement)},
            client="api", ts=self.now,
        ))
        return fb

    # ---- summary ----------------------------------------------------------
    async def summary(self, days: int = 30, scope: str = "me") -> Dict[str, Any]:
        scope_all = scope == "all" and self.is_admin
        since = self.now - timedelta(days=days)
        await self.hub.flush()  # make sure what was just recorded is visible
        cid = None if scope_all else self.creator_id
        events = await self.repo.list_events(cid, since)
        feedback = await self.repo.list_feedback(cid, since)
        out = summarize(events, feedback, days, now=self.now)
        out["scope"] = "all" if scope_all else "me"
        out["hub"] = dict(self.hub.stats)
        return out
