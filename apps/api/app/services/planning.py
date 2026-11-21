"""
Planning service — orchestrates analytics, ideas, the Kanban board and the
prediction-review loop on top of a PlanningRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.repositories.base import PlanningRepository
from app.repositories.domain import (
    PIPELINE,
    STAGES,
    normalize_stage,
    Card,
    CardEvent,
    Review,
    TransitionError,
    next_slot_datetime,
    validate_transition,
)
from app.services.analytics.engine import Analysis
from app.services.analytics.ideas import Idea, IdeaGenerator
from app.services.analytics.next_project import NextProject, NextProjectGenerator
from app.services.analytics.trends import TrendRecord
from app.services.analytics.learning import (
    Calibration,
    accuracy_summary,
    auto_match_post,
    review_prediction,
)
from app.services.analytics.prediction import predict
from app.services.analytics.records import PLATFORM_FORMATS, PostRecord, parse_dt


class NotFound(LookupError):
    pass


class PlanningService:
    def __init__(self, repo: PlanningRepository, creator_id: str, posts: Sequence[PostRecord],
                 tz: str = "UTC", now: Optional[datetime] = None):
        self.repo = repo
        self.creator_id = creator_id
        self.posts = list(posts)
        self.tz = tz
        self.analysis = Analysis(self.posts, tz=tz, now=now)

    # ---- calibration lookup used by the generator ----------------------
    async def _calibrations(self) -> Dict[tuple, Calibration]:
        return {(c.platform, c.content_type): c for c in await self.repo.list_calibrations(self.creator_id)}

    # ---- analytics -------------------------------------------------------
    def overview(self) -> Dict[str, Any]:
        return self.analysis.overview()

    def patterns(self) -> Dict[str, Any]:
        return self.analysis.patterns()

    async def learning(self) -> Dict[str, Any]:
        reviews = await self.repo.list_reviews(self.creator_id)
        cals = await self.repo.list_calibrations(self.creator_id)
        review_dicts = [r.to_dict() for r in reviews]
        by_platform: Dict[str, Any] = {}
        for pl in PLATFORM_FORMATS:
            subset = [r for r in review_dicts if (r.get("actual") or {}).get("post_id") and
                      any(p.id == r["actual"]["post_id"] and p.platform == pl for p in self.posts)]
            by_platform[pl] = accuracy_summary(subset)
        return {
            "accuracy": accuracy_summary(review_dicts),
            "by_platform": by_platform,
            "calibrations": [c.to_dict() for c in cals],
            "reviews": list(reversed(review_dicts))[:20],
        }

    # ---- ideas ----------------------------------------------------------
    async def generate_ideas(self, count: int = 6, seed: Optional[int] = None) -> List[Idea]:
        cals = await self._calibrations()

        def lookup(platform: str, ct: str):
            c = cals.get((platform, ct))
            return (c.factor, c.samples) if c else (1.0, 0)

        if seed is None:
            seed = len(await self.repo.list_ideas(self.creator_id)) // max(count, 1)
        ideas = IdeaGenerator(self.analysis, lookup, seed=seed).generate(count)
        return await self.repo.add_ideas(self.creator_id, ideas)

    async def next_project(self, trends: Sequence[TrendRecord], exclude_trend_ids: Sequence[str] = (),
                           platform: Optional[str] = None, enrichment_status: Optional[str] = None) -> NextProject:
        """One-click project from the best current trend (falls back to analytics when nothing fits)."""
        cals = await self._calibrations()

        def lookup(p: str, ct: str):
            c = cals.get((p, ct))
            return (c.factor, c.samples) if c else (1.0, 0)

        # Never propose the same trend twice: skip trends this creator already has an idea for.
        used = {i.trend_id for i in await self.repo.list_ideas(self.creator_id) if i.trend_id}
        existing = len(await self.repo.list_ideas(self.creator_id))
        result = NextProjectGenerator(self.analysis, trends, lookup, seed=existing).generate(
            exclude_trend_ids=list(exclude_trend_ids) + sorted(used), platform=platform)
        result.idea.enrichment_status = enrichment_status
        await self.repo.add_ideas(self.creator_id, [result.idea])
        return result

    async def get_idea(self, idea_id: str) -> Idea:
        idea = await self.repo.get_idea(self.creator_id, idea_id)
        if idea is None:
            raise NotFound("Idea not found")
        return idea

    async def set_enrichment_status(self, idea_id: str, status: Optional[str]) -> None:
        await self.repo.set_enrichment_status(self.creator_id, idea_id, status)

    async def list_ideas(self, status: Optional[str] = None) -> List[Idea]:
        return await self.repo.list_ideas(self.creator_id, status)

    async def dismiss_idea(self, idea_id: str) -> Idea:
        idea = await self.repo.set_idea_status(self.creator_id, idea_id, "rejected")
        if idea is None:
            raise NotFound("Idea not found")
        return idea

    async def idea_to_board(self, idea_id: str) -> Card:
        idea = await self.repo.get_idea(self.creator_id, idea_id)
        if idea is None:
            raise NotFound("Idea not found")
        existing = [c for c in await self.repo.list_cards(self.creator_id) if c.suggestion_id == idea.id]
        if existing:
            return existing[0]

        prediction = idea.prediction
        if not prediction:
            # Trend/LLM suggestions have no forecast yet — compute one now so it can be reviewed later
            platform = idea.platform or "YouTube"
            ct = idea.content_type or PLATFORM_FORMATS[platform][0]
            slot = (self.analysis.best_slots(platform, 1) or [None])[0]
            cal = await self.repo.get_calibration(self.creator_id, platform, ct)
            prediction = predict(self.analysis, platform, ct, idea.topics, slot,
                                 cal.factor if cal else 1.0, cal.samples if cal else 0).to_dict()
            idea.platform, idea.content_type, idea.recommended_slot = platform, ct, slot

        card = Card(
            creator_id=self.creator_id,
            title=idea.title,
            hook=idea.hook,
            outline=list(idea.outline),
            platform=idea.platform,
            content_type=idea.content_type,
            topics=list(idea.topics),
            stage="idea",
            position=await self._next_position("idea"),
            suggestion_id=idea.id,
            prediction=prediction,
            recommended_slot=idea.recommended_slot,
            strategy=idea.strategy,
            rationale=idea.rationale,
            notes=self._kit_notes(idea.kit),
        )
        card = await self.repo.save_card(card)
        await self.repo.add_event(CardEvent(card_id=card.id, from_stage=None, to_stage="idea", note="Created from idea"))
        await self.repo.set_idea_status(self.creator_id, idea.id, "converted_to_kanban")
        return card

    @staticmethod
    def _kit_notes(kit: Optional[Dict[str, Any]]) -> str:
        """Render a production kit as plain-text notes on the Kanban card."""
        if not kit:
            return ""
        lines: List[str] = []
        window = kit.get("trend_window")
        if window:
            lines.append(f"⏱ Publish within {window['publish_within_hours']}h — {window['reason']}")
        if kit.get("thumbnail"):
            lines.append(f"🖼 Thumbnail: {kit['thumbnail'].get('text', '')} — {kit['thumbnail'].get('concept', '')}")
        if kit.get("shot_list"):
            lines.append("🎬 Shot list:")
            lines += [f"  • {s}" for s in kit["shot_list"]]
        for stage, items in (kit.get("checklist") or {}).items():
            lines.append(f"☐ {stage.capitalize()}: " + "; ".join(items))
        if kit.get("caption"):
            lines.append(f"✍ Caption: {kit['caption']}")
        if kit.get("hashtags"):
            lines.append("# " + " ".join(kit["hashtags"]))
        return "\n".join(lines)

    # ---- kanban ---------------------------------------------------------
    async def _next_position(self, stage: str) -> int:
        cards = [c for c in await self.repo.list_cards(self.creator_id) if c.stage == stage]
        return (max((c.position for c in cards), default=-1) + 1)

    async def board(self) -> Dict[str, Any]:
        cards = await self.repo.list_cards(self.creator_id)
        reviews = {r.card_id: r for r in await self.repo.list_reviews(self.creator_id)}
        columns = []
        for stage in PIPELINE:
            members = [c for c in cards if c.stage == stage]
            if stage == "published":
                # Reviewed cards stay in the Published column (terminal sub-state), after the un-reviewed ones.
                members = sorted(members, key=lambda c: (c.position, c.created_at)) + \
                          sorted([c for c in cards if c.stage == "reviewed"], key=lambda c: (c.position, c.created_at))
            else:
                members.sort(key=lambda c: (c.position, c.created_at))
            columns.append({
                "stage": stage,
                "cards": [self._card_view(c, reviews.get(c.id)) for c in members],
            })
        return {"columns": columns, "total": len(cards)}

    def _card_view(self, card: Card, review: Optional[Review] = None) -> Dict[str, Any]:
        d = card.to_dict()
        d["review"] = review.to_dict() if review else None
        if card.post_id:
            post = next((p for p in self.posts if p.id == card.post_id), None)
            d["linked_post"] = post.to_feed_dict() if post else None
        else:
            d["linked_post"] = None
        return d

    async def create_card(self, data: Dict[str, Any]) -> Card:
        platform = data.get("platform") or "YouTube"
        ct = data.get("content_type") or PLATFORM_FORMATS.get(platform, ("Long-form",))[0]
        topics = list(data.get("topics") or [])
        slot = data.get("recommended_slot") or (self.analysis.best_slots(platform, 1) or [None])[0]
        cal = await self.repo.get_calibration(self.creator_id, platform, ct)
        prediction = data.get("prediction") or predict(
            self.analysis, platform, ct, topics, slot, cal.factor if cal else 1.0, cal.samples if cal else 0
        ).to_dict()
        stage = normalize_stage(data.get("stage") or "idea")
        if stage not in STAGES or stage == "reviewed":
            raise TransitionError(f"Cannot create a card directly in stage '{stage}'")
        card = Card(
            creator_id=self.creator_id,
            title=data["title"],
            hook=data.get("hook") or "",
            outline=list(data.get("outline") or []),
            platform=platform,
            content_type=ct,
            topics=topics,
            stage=stage,
            position=await self._next_position(stage),
            prediction=prediction,
            recommended_slot=slot,
            strategy=data.get("strategy") or "manual",
            rationale=data.get("rationale") or "Created manually.",
            notes=data.get("notes") or "",
            scheduled_for=data.get("scheduled_for"),
        )
        card = await self.repo.save_card(card)
        await self.repo.add_event(CardEvent(card_id=card.id, from_stage=None, to_stage=stage, note="Created manually"))
        return card

    async def get_card(self, card_id: str) -> Card:
        card = await self.repo.get_card(self.creator_id, card_id)
        if card is None:
            raise NotFound("Card not found")
        return card

    async def card_detail(self, card_id: str) -> Dict[str, Any]:
        card = await self.get_card(card_id)
        view = self._card_view(card, await self.repo.get_review(card.id))
        view["events"] = [e.to_dict() for e in await self.repo.list_events(card.id)]
        return view

    async def update_card(self, card_id: str, data: Dict[str, Any]) -> Card:
        card = await self.get_card(card_id)
        editable = ("title", "hook", "outline", "topics", "notes", "scheduled_for", "published_at", "platform", "content_type")
        changed_forecast_inputs = False
        for k in editable:
            if k in data and data[k] is not None:
                if k in ("platform", "content_type", "topics") and getattr(card, k) != data[k]:
                    changed_forecast_inputs = True
                setattr(card, k, data[k])
        if changed_forecast_inputs and card.stage in PIPELINE[:-1]:
            cal = await self.repo.get_calibration(self.creator_id, card.platform, card.content_type)
            card.prediction = predict(self.analysis, card.platform, card.content_type, card.topics,
                                      card.recommended_slot, cal.factor if cal else 1.0, cal.samples if cal else 0).to_dict()
        return await self.repo.save_card(card)

    async def move_card(self, card_id: str, stage: str, position: Optional[int] = None, note: str = "") -> Card:
        card = await self.get_card(card_id)
        from_stage = card.stage
        stage = normalize_stage(stage)
        validate_transition(from_stage, stage)

        if stage == "editing" and not card.scheduled_for:
            # Entering the edit suite: pencil in the next recommended publishing slot
            nxt = next_slot_datetime(card.recommended_slot, self.analysis.now)
            card.scheduled_for = nxt.isoformat() if nxt else None
        if stage == "published" and not card.published_at:
            card.published_at = datetime.now(timezone.utc).isoformat()
            # Try to find the real post automatically
            if not card.post_id:
                match = auto_match_post(self.posts, card.title, card.platform, card.content_type,
                                        parse_dt(card.published_at))
                if match:
                    card.post_id = match[0].id

        # Re-order siblings in the target column
        siblings = [c for c in await self.repo.list_cards(self.creator_id) if c.stage == stage and c.id != card.id]
        siblings.sort(key=lambda c: (c.position, c.created_at))
        if position is None or position > len(siblings):
            position = len(siblings)
        siblings.insert(max(position, 0), card)
        for idx, c in enumerate(siblings):
            if c.position != idx or c.id == card.id:
                c.position = idx
                if c.id != card.id:
                    await self.repo.save_card(c)
        card.stage = stage
        card = await self.repo.save_card(card)
        if from_stage != stage:
            await self.repo.add_event(CardEvent(card_id=card.id, from_stage=from_stage, to_stage=stage, note=note))
        return card

    async def delete_card(self, card_id: str) -> None:
        if not await self.repo.delete_card(self.creator_id, card_id):
            raise NotFound("Card not found")

    async def events(self, card_id: str) -> List[Dict[str, Any]]:
        await self.get_card(card_id)
        return [e.to_dict() for e in await self.repo.list_events(card_id)]

    # ---- publish → review → learn ---------------------------------------
    async def link_post(self, card_id: str, post_id: Optional[str] = None, auto: bool = False) -> Card:
        card = await self.get_card(card_id)
        if post_id:
            post = next((p for p in self.posts if p.id == post_id or p.external_post_id == post_id), None)
            if post is None:
                raise NotFound("Post not found in your synced content")
        elif auto:
            match = auto_match_post(self.posts, card.title, card.platform, card.content_type,
                                    parse_dt(card.published_at) or parse_dt(card.scheduled_for))
            if match is None:
                raise NotFound("No matching published post found — pick it manually")
            post = match[0]
        else:
            raise NotFound("post_id or auto=true is required")

        card.post_id = post.id
        if not card.published_at and post.published_at:
            card.published_at = post.published_at.isoformat()
        if card.platform != post.platform or card.content_type != post.content_type:
            # The creator shipped it in a different format than planned — record it, keep the forecast.
            card.notes = (card.notes + "\n" if card.notes else "") + \
                f"Published as {post.content_type} on {post.platform} (planned {card.content_type} on {card.platform})."
        card = await self.repo.save_card(card)
        await self.repo.add_event(CardEvent(card_id=card.id, from_stage=card.stage, to_stage=card.stage,
                                            note=f"Linked to post “{post.title[:60]}”"))
        return card

    async def review_card(self, card_id: str, min_age_days: float = 0.0) -> Dict[str, Any]:
        card = await self.get_card(card_id)
        if card.stage not in ("published", "reviewed"):
            raise TransitionError("Move the card to 'published' (and link the post) before reviewing it.")
        if not card.post_id:
            raise TransitionError("Link the published post to this card first.")
        if not card.prediction:
            raise TransitionError("This card has no prediction to review.")
        post = next((p for p in self.posts if p.id == card.post_id), None)
        if post is None:
            raise NotFound("Linked post is no longer in your synced content")
        age = post.age_days(self.analysis.now) or 0.0
        if age < min_age_days:
            raise TransitionError(f"Post is only {age:.1f} days old; wait {min_age_days:.0f} days for metrics to settle.")

        cal = await self.repo.get_calibration(self.creator_id, post.platform, post.content_type)
        result, new_cal = review_prediction(card.prediction, post, self.analysis, cal, self.creator_id,
                                            card.recommended_slot, self.tz)
        await self.repo.upsert_calibration(new_cal)
        review = Review(card_id=card.id, creator_id=self.creator_id, post_id=post.id, result=result.to_dict())
        await self.repo.add_review(review)

        from_stage = card.stage
        card.stage = "reviewed"
        card.position = await self._next_position("reviewed")
        card = await self.repo.save_card(card)
        await self.repo.add_event(CardEvent(card_id=card.id, from_stage=from_stage, to_stage="reviewed",
                                            note=f"Reviewed: {result.verdict} ({result.views_ratio}x forecast)"))
        return self._card_view(card, review)

    async def get_review(self, card_id: str) -> Dict[str, Any]:
        await self.get_card(card_id)
        review = await self.repo.get_review(card_id)
        if review is None:
            raise NotFound("No review yet")
        return review.to_dict()
