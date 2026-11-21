"""
SQLAlchemy-backed planning repository (non-mock mode).

All queries are scoped by creator_id — a card/idea belonging to another
creator is indistinguishable from a missing one.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.planning import CreatorCalibration, PredictionReview, ProductionCard, ProductionEvent
from app.models.suggestion import ContentSuggestion
from app.repositories.domain import Card, CardEvent, Review
from app.services.analytics.ideas import Idea
from app.services.analytics.learning import Calibration
from app.services.analytics.records import parse_dt


def _uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ---- mappers ---------------------------------------------------------------
def idea_from_row(row: ContentSuggestion) -> Idea:
    return Idea(
        id=str(row.id),
        title=row.title,
        hook=row.hook or "",
        outline=list(row.outline or []),
        platform=row.platform or "YouTube",
        content_type=row.content_type or "Long-form",
        topics=list(row.topics or []),
        strategy=row.strategy or "trend",
        rationale=row.reasoning or "",
        recommended_slot=row.recommended_slot,
        prediction=row.prediction or {},
        confidence_score=float(row.confidence_score or 0.0),
        description=row.description or "",
        source=row.source or "trend",
        status=row.status,
        created_at=_iso(row.created_at) or "",
        trend_id=str(row.trend_id) if row.trend_id else None,
        kit=dict(row.kit or {}),
        enrichment_status=row.enrichment_status,
    )


def card_from_row(row: ProductionCard) -> Card:
    return Card(
        id=str(row.id),
        creator_id=str(row.creator_id),
        title=row.title,
        hook=row.hook or "",
        outline=list(row.outline or []),
        platform=row.platform,
        content_type=row.content_type,
        topics=list(row.topics or []),
        stage=row.stage,
        position=row.position or 0,
        suggestion_id=str(row.suggestion_id) if row.suggestion_id else None,
        post_id=str(row.post_id) if row.post_id else None,
        scheduled_for=_iso(row.scheduled_for),
        published_at=_iso(row.published_at),
        prediction=row.prediction,
        recommended_slot=row.recommended_slot,
        strategy=row.strategy,
        rationale=row.rationale,
        notes=row.notes or "",
        created_at=_iso(row.created_at) or "",
        updated_at=_iso(row.updated_at) or "",
    )


def review_from_row(row: PredictionReview) -> Review:
    return Review(
        id=str(row.id),
        card_id=str(row.card_id),
        creator_id=str(row.creator_id),
        post_id=str(row.post_id) if row.post_id else None,
        result=dict(row.result or {}),
        reviewed_at=_iso(row.reviewed_at) or "",
    )


def cal_from_row(row: CreatorCalibration) -> Calibration:
    return Calibration(
        creator_id=str(row.creator_id),
        platform=row.platform,
        content_type=row.content_type,
        factor=float(row.factor),
        samples=int(row.samples),
        updated_at=_iso(row.updated_at) or "",
    )


class SqlPlanningRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---- ideas ----------------------------------------------------------
    async def list_ideas(self, creator_id: str, status: Optional[str] = None) -> List[Idea]:
        stmt = select(ContentSuggestion).where(ContentSuggestion.creator_id == _uuid(creator_id))
        if status:
            stmt = stmt.where(ContentSuggestion.status == status)
        stmt = stmt.order_by(ContentSuggestion.created_at.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return [idea_from_row(r) for r in rows]

    async def get_idea(self, creator_id: str, idea_id: str) -> Optional[Idea]:
        iid = _uuid(idea_id)
        if iid is None:
            return None
        row = await self.db.get(ContentSuggestion, iid)
        if row is None or str(row.creator_id) != str(creator_id):
            return None
        return idea_from_row(row)

    async def add_ideas(self, creator_id: str, ideas: Sequence[Idea]) -> List[Idea]:
        out = []
        for idea in ideas:
            row = ContentSuggestion(
                id=_uuid(idea.id) or uuid.uuid4(),
                creator_id=_uuid(creator_id),
                title=idea.title,
                description=idea.description or idea.rationale,
                reasoning=idea.rationale,
                confidence_score=idea.confidence_score,
                status=idea.status,
                source=idea.source,
                hook=idea.hook,
                outline=idea.outline,
                platform=idea.platform,
                content_type=idea.content_type,
                topics=idea.topics,
                strategy=idea.strategy,
                recommended_slot=idea.recommended_slot,
                prediction=idea.prediction,
                trend_id=_uuid(idea.trend_id),
                kit=idea.kit or None,
                enrichment_status=idea.enrichment_status,
            )
            self.db.add(row)
            out.append(idea)
        await self.db.flush()
        return out

    async def set_enrichment_status(self, creator_id: str, idea_id: str, status: Optional[str]) -> None:
        iid = _uuid(idea_id)
        row = await self.db.get(ContentSuggestion, iid) if iid else None
        if row is not None and str(row.creator_id) == str(creator_id):
            row.enrichment_status = status
            await self.db.flush()

    async def set_idea_status(self, creator_id: str, idea_id: str, status: str) -> Optional[Idea]:
        iid = _uuid(idea_id)
        row = await self.db.get(ContentSuggestion, iid) if iid else None
        if row is None or str(row.creator_id) != str(creator_id):
            return None
        row.status = status
        await self.db.flush()
        return idea_from_row(row)

    # ---- cards ----------------------------------------------------------
    async def list_cards(self, creator_id: str) -> List[Card]:
        stmt = (
            select(ProductionCard)
            .where(ProductionCard.creator_id == _uuid(creator_id))
            .order_by(ProductionCard.stage, ProductionCard.position, ProductionCard.created_at)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [card_from_row(r) for r in rows]

    async def _card_row(self, creator_id: str, card_id: str) -> Optional[ProductionCard]:
        cid = _uuid(card_id)
        row = await self.db.get(ProductionCard, cid) if cid else None
        if row is None or str(row.creator_id) != str(creator_id):
            return None
        return row

    async def get_card(self, creator_id: str, card_id: str) -> Optional[Card]:
        row = await self._card_row(creator_id, card_id)
        return card_from_row(row) if row else None

    async def save_card(self, card: Card) -> Card:
        row = await self._card_row(card.creator_id, card.id)
        if row is None:
            row = ProductionCard(id=_uuid(card.id) or uuid.uuid4(), creator_id=_uuid(card.creator_id))
            self.db.add(row)
        row.title = card.title
        row.hook = card.hook
        row.outline = card.outline
        row.platform = card.platform
        row.content_type = card.content_type
        row.topics = card.topics
        row.strategy = card.strategy
        row.rationale = card.rationale
        row.stage = card.stage
        row.position = card.position
        row.suggestion_id = _uuid(card.suggestion_id)
        row.post_id = _uuid(card.post_id)
        row.scheduled_for = parse_dt(card.scheduled_for)
        row.published_at = parse_dt(card.published_at)
        row.prediction = card.prediction
        row.recommended_slot = card.recommended_slot
        row.notes = card.notes
        await self.db.flush()
        await self.db.refresh(row)
        return card_from_row(row)

    async def delete_card(self, creator_id: str, card_id: str) -> bool:
        row = await self._card_row(creator_id, card_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def add_event(self, event: CardEvent) -> CardEvent:
        self.db.add(ProductionEvent(
            id=_uuid(event.id), card_id=_uuid(event.card_id),
            from_stage=event.from_stage, to_stage=event.to_stage, note=event.note,
        ))
        await self.db.flush()
        return event

    async def list_events(self, card_id: str) -> List[CardEvent]:
        stmt = select(ProductionEvent).where(ProductionEvent.card_id == _uuid(card_id)).order_by(ProductionEvent.created_at)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [CardEvent(id=str(r.id), card_id=str(r.card_id), from_stage=r.from_stage, to_stage=r.to_stage,
                          note=r.note or "", created_at=_iso(r.created_at) or "") for r in rows]

    # ---- reviews & calibration -----------------------------------------
    async def add_review(self, review: Review) -> Review:
        existing = (await self.db.execute(
            select(PredictionReview).where(PredictionReview.card_id == _uuid(review.card_id))
        )).scalar_one_or_none()
        if existing:
            await self.db.delete(existing)
            await self.db.flush()
        self.db.add(PredictionReview(
            id=_uuid(review.id), card_id=_uuid(review.card_id), creator_id=_uuid(review.creator_id),
            post_id=_uuid(review.post_id), verdict=review.result.get("verdict", "on_target"),
            views_ratio=float(review.result.get("views_ratio", 1.0)),
            abs_pct_error=float(review.result.get("abs_pct_error", 0.0)),
            result=review.result,
        ))
        await self.db.flush()
        return review

    async def get_review(self, card_id: str) -> Optional[Review]:
        row = (await self.db.execute(
            select(PredictionReview).where(PredictionReview.card_id == _uuid(card_id))
        )).scalar_one_or_none()
        return review_from_row(row) if row else None

    async def list_reviews(self, creator_id: str) -> List[Review]:
        stmt = select(PredictionReview).where(PredictionReview.creator_id == _uuid(creator_id)).order_by(PredictionReview.reviewed_at)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [review_from_row(r) for r in rows]

    async def get_calibration(self, creator_id: str, platform: str, content_type: str) -> Optional[Calibration]:
        row = (await self.db.execute(
            select(CreatorCalibration).where(
                CreatorCalibration.creator_id == _uuid(creator_id),
                CreatorCalibration.platform == platform,
                CreatorCalibration.content_type == content_type,
            )
        )).scalar_one_or_none()
        return cal_from_row(row) if row else None

    async def upsert_calibration(self, cal: Calibration) -> Calibration:
        row = (await self.db.execute(
            select(CreatorCalibration).where(
                CreatorCalibration.creator_id == _uuid(cal.creator_id),
                CreatorCalibration.platform == cal.platform,
                CreatorCalibration.content_type == cal.content_type,
            )
        )).scalar_one_or_none()
        if row is None:
            row = CreatorCalibration(creator_id=_uuid(cal.creator_id), platform=cal.platform, content_type=cal.content_type)
            self.db.add(row)
        row.factor = cal.factor
        row.samples = cal.samples
        await self.db.flush()
        return cal

    async def list_calibrations(self, creator_id: str) -> List[Calibration]:
        stmt = select(CreatorCalibration).where(CreatorCalibration.creator_id == _uuid(creator_id))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [cal_from_row(r) for r in rows]
