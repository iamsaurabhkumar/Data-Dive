"""
Seeds the in-memory planning repository in MOCK_MODE so the demo board,
idea list and learning page are populated on first load.

Everything is derived from the deterministic mock feed, so the seeded
predictions/reviews are consistent with what the analytics pages show.
"""
from __future__ import annotations

from datetime import timedelta

from app.repositories.domain import Card, CardEvent, Review
from app.repositories.memory import MemoryPlanningRepository
from app.services.analytics.engine import Analysis
from app.services.analytics.ideas import IdeaGenerator
from app.services.analytics.learning import review_prediction
from app.services.analytics.prediction import predict
from app.services.analytics.records import PostRecord
from app.services.mock_data import MOCK_NOW, get_mock_feed


def seed_mock_planning(repo: MemoryPlanningRepository, creator_id: str) -> None:
    posts = [PostRecord.from_feed_dict(p) for p in get_mock_feed()]
    analysis = Analysis(posts, now=MOCK_NOW)
    gen = IdeaGenerator(analysis, seed=7)
    ideas = gen.generate(6)

    # Pending ideas (two are converted into cards below)
    for idea in ideas:
        stored = idea
        stored._creator_id = creator_id  # type: ignore[attr-defined]
        repo._ideas[stored.id] = stored

    def add_card(card: Card, note: str) -> Card:
        repo._cards[card.id] = card
        repo._events.setdefault(card.id, []).append(CardEvent(card_id=card.id, from_stage=None, to_stage="idea", note=note))
        return card

    def moved(card: Card, stages: list[str]) -> None:
        prev = card.stage
        for s in stages:
            repo._events.setdefault(card.id, []).append(CardEvent(card_id=card.id, from_stage=prev, to_stage=s))
            prev = s
        card.stage = prev

    # 1) two ideas already on the board
    for idx, idea in enumerate(ideas[:2]):
        idea.status = "converted_to_kanban"
        c = Card(creator_id=creator_id, title=idea.title, hook=idea.hook, outline=list(idea.outline),
                 platform=idea.platform, content_type=idea.content_type, topics=list(idea.topics),
                 suggestion_id=idea.id, prediction=idea.prediction, recommended_slot=idea.recommended_slot,
                 strategy=idea.strategy, rationale=idea.rationale, stage="idea", position=idx)
        add_card(c, "Created from idea")
    # move the second one to planning
    second = [c for c in repo._cards.values() if c.creator_id == creator_id][1]
    moved(second, ["scripting"])
    second.position = 0
    second.notes = "Script draft due Friday. Reuse B-roll from the studio tour."

    # 2) a card being filmed and one in the edit
    prod = Card(creator_id=creator_id, title="Studio Tour 2.0 — Everything That Changed", hook="Last year's tour got 40k views. This one fixes everything you complained about.",
                outline=["Cold open: the before shot", "Walkthrough: desk, lighting, audio", "Cost breakdown", "CTA: comment your setup"],
                platform="YouTube", content_type="Long-form", topics=["studio"], strategy="double_down",
                rationale="Studio content is your most consistent performer on YouTube.",
                prediction=predict(analysis, "YouTube", "Long-form", ["studio"], analysis.best_slots("YouTube", 1)[0]).to_dict(),
                recommended_slot=analysis.best_slots("YouTube", 1)[0], stage="idea", position=0)
    add_card(prod, "Created manually")
    moved(prod, ["scripting", "filming"])

    sched = Card(creator_id=creator_id, title="3 Camera Settings I Never Change", hook="Auto mode is costing you. Here are the three dials I lock on every shoot.",
                 outline=["0–3s hook", "Setting 1: shutter", "Setting 2: white balance", "Setting 3: picture profile", "CTA: save"],
                 platform="Instagram", content_type="Reel", topics=["camera"], strategy="cross_post",
                 rationale="Camera content travels well to Reels.",
                 prediction=predict(analysis, "Instagram", "Reel", ["camera"], analysis.best_slots("Instagram", 1)[0]).to_dict(),
                 recommended_slot=analysis.best_slots("Instagram", 1)[0], stage="idea", position=0,
                 scheduled_for=(MOCK_NOW + timedelta(days=3)).replace(hour=18, minute=0).isoformat())
    add_card(sched, "Created manually")
    moved(sched, ["scripting", "filming", "editing"])

    # 3) a published + reviewed card linked to a real mock post, so the learning page has data
    reviewed_targets = [p for p in posts if p.platform == "YouTube" and p.content_type == "Long-form"]
    reviewed_targets.sort(key=lambda p: p.published_at or MOCK_NOW)
    target = reviewed_targets[-3]  # a recent-ish long-form video
    slot = analysis.best_slots("YouTube", 1)[0]
    pred = predict(analysis, "YouTube", "Long-form", target.topics[:1], slot).to_dict()
    pub = Card(creator_id=creator_id, title=target.title, hook="The result first, then how I got there.",
               outline=["Cold open", "Context", "Walkthrough", "Result", "CTA"],
               platform="YouTube", content_type="Long-form", topics=target.topics[:2], strategy="double_down",
               rationale="Planned from a winning topic.", prediction=pred, recommended_slot=slot,
               stage="idea", position=0, post_id=target.id,
               published_at=target.published_at.isoformat() if target.published_at else None)
    add_card(pub, "Created from idea")
    moved(pub, ["scripting", "filming", "editing", "published"])
    result, cal = review_prediction(pred, target, analysis, None, creator_id, slot)
    repo._cals[(creator_id, "YouTube", "Long-form")] = cal
    repo._reviews[pub.id] = Review(card_id=pub.id, creator_id=creator_id, post_id=target.id, result=result.to_dict())
    repo._events[pub.id].append(CardEvent(card_id=pub.id, from_stage="published", to_stage="reviewed",
                                          note=f"Reviewed: {result.verdict} ({result.views_ratio}x forecast)"))
    pub.stage = "reviewed"

    # 4) a second published card, still waiting for review (linked automatically)
    target2 = [p for p in posts if p.platform == "Instagram" and p.content_type == "Reel"][2]
    slot2 = analysis.best_slots("Instagram", 1)[0]
    pub2 = Card(creator_id=creator_id, title=target2.title, hook="Sound on — this one is all in the cuts.",
                outline=["Hook", "Problem", "Fix", "Proof", "CTA"], platform="Instagram", content_type="Reel",
                topics=target2.topics[:2], strategy="double_down", rationale="Reels are your strongest format.",
                prediction=predict(analysis, "Instagram", "Reel", target2.topics[:1], slot2).to_dict(),
                recommended_slot=slot2, stage="idea", position=0, post_id=target2.id,
                published_at=target2.published_at.isoformat() if target2.published_at else None)
    add_card(pub2, "Created from idea")
    moved(pub2, ["scripting", "filming", "editing", "published"])
