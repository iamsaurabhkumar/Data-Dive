"""
In-memory repository used in MOCK_MODE (and tests).

State lives for the lifetime of the process. A seed hook lets mock mode
start with a populated board so the demo is meaningful.
"""
from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional, Sequence

from app.repositories.domain import Card, CardEvent, Review, now_iso
from app.services.analytics.ideas import Idea
from app.services.analytics.learning import Calibration


class MemoryPlanningRepository:
    def __init__(self, seeder: Optional[Callable[["MemoryPlanningRepository", str], None]] = None):
        self._ideas: Dict[str, Idea] = {}
        self._cards: Dict[str, Card] = {}
        self._events: Dict[str, List[CardEvent]] = {}
        self._reviews: Dict[str, Review] = {}
        self._cals: Dict[tuple, Calibration] = {}
        self._seeded: set = set()
        self._seeder = seeder

    def _ensure_seed(self, creator_id: str) -> None:
        if self._seeder and creator_id not in self._seeded:
            self._seeded.add(creator_id)
            self._seeder(self, creator_id)

    def reset(self) -> None:
        self.__init__(self._seeder)

    # ---- ideas ----------------------------------------------------------
    async def list_ideas(self, creator_id: str, status: Optional[str] = None) -> List[Idea]:
        self._ensure_seed(creator_id)
        out = [i for i in self._ideas.values() if getattr(i, "_creator_id", None) == creator_id]
        if status:
            out = [i for i in out if i.status == status]
        out.sort(key=lambda i: i.created_at, reverse=True)
        return [copy.deepcopy(i) for i in out]

    async def get_idea(self, creator_id: str, idea_id: str) -> Optional[Idea]:
        self._ensure_seed(creator_id)
        i = self._ideas.get(idea_id)
        if i is None or getattr(i, "_creator_id", None) != creator_id:
            return None
        return copy.deepcopy(i)

    async def add_ideas(self, creator_id: str, ideas: Sequence[Idea]) -> List[Idea]:
        self._ensure_seed(creator_id)
        for idea in ideas:
            stored = copy.deepcopy(idea)
            stored._creator_id = creator_id  # type: ignore[attr-defined]
            self._ideas[stored.id] = stored
        return [copy.deepcopy(i) for i in ideas]

    async def set_enrichment_status(self, creator_id: str, idea_id: str, status: Optional[str]) -> None:
        i = self._ideas.get(idea_id)
        if i is not None and getattr(i, "_creator_id", None) == creator_id:
            i.enrichment_status = status

    async def set_idea_status(self, creator_id: str, idea_id: str, status: str) -> Optional[Idea]:
        i = self._ideas.get(idea_id)
        if i is None or getattr(i, "_creator_id", None) != creator_id:
            return None
        i.status = status
        return copy.deepcopy(i)

    # ---- cards ----------------------------------------------------------
    async def list_cards(self, creator_id: str) -> List[Card]:
        self._ensure_seed(creator_id)
        out = [c for c in self._cards.values() if c.creator_id == creator_id]
        out.sort(key=lambda c: (c.stage, c.position, c.created_at))
        return [copy.deepcopy(c) for c in out]

    async def get_card(self, creator_id: str, card_id: str) -> Optional[Card]:
        self._ensure_seed(creator_id)
        c = self._cards.get(card_id)
        return copy.deepcopy(c) if c and c.creator_id == creator_id else None

    async def save_card(self, card: Card) -> Card:
        card.updated_at = now_iso()
        self._cards[card.id] = copy.deepcopy(card)
        return copy.deepcopy(card)

    async def delete_card(self, creator_id: str, card_id: str) -> bool:
        c = self._cards.get(card_id)
        if not c or c.creator_id != creator_id:
            return False
        del self._cards[card_id]
        self._events.pop(card_id, None)
        self._reviews.pop(card_id, None)
        return True

    async def add_event(self, event: CardEvent) -> CardEvent:
        self._events.setdefault(event.card_id, []).append(copy.deepcopy(event))
        return event

    async def list_events(self, card_id: str) -> List[CardEvent]:
        return [copy.deepcopy(e) for e in self._events.get(card_id, [])]

    # ---- reviews & calibration -----------------------------------------
    async def add_review(self, review: Review) -> Review:
        self._reviews[review.card_id] = copy.deepcopy(review)
        return review

    async def get_review(self, card_id: str) -> Optional[Review]:
        r = self._reviews.get(card_id)
        return copy.deepcopy(r) if r else None

    async def list_reviews(self, creator_id: str) -> List[Review]:
        self._ensure_seed(creator_id)
        out = [r for r in self._reviews.values() if r.creator_id == creator_id]
        out.sort(key=lambda r: r.reviewed_at)
        return [copy.deepcopy(r) for r in out]

    async def get_calibration(self, creator_id: str, platform: str, content_type: str) -> Optional[Calibration]:
        self._ensure_seed(creator_id)
        c = self._cals.get((creator_id, platform, content_type))
        return copy.deepcopy(c) if c else None

    async def upsert_calibration(self, cal: Calibration) -> Calibration:
        self._cals[(cal.creator_id, cal.platform, cal.content_type)] = copy.deepcopy(cal)
        return cal

    async def list_calibrations(self, creator_id: str) -> List[Calibration]:
        self._ensure_seed(creator_id)
        return [copy.deepcopy(c) for k, c in self._cals.items() if k[0] == creator_id]
