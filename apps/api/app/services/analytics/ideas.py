"""
Tailored content-idea generator.

Ideas are produced from the creator's own patterns (topics × formats × slots)
using a library of proven title angles, hook formulas and format-specific
outlines. Generation is deterministic for a given (data, seed) so that ideas
— and their predictions — are reproducible and reviewable.

Strategies (diversified so a batch is not six variations of one topic):
  double_down  — strongest topic in its strongest format
  cross_post   — a winning topic from one platform, adapted to the other platform's best format
  remix        — cut a top-performing long piece down into short-form (or expand a short into long-form)
  revive       — an under-performing topic re-framed with a high-contrast angle (low-risk experiment)
  series       — a multi-part deep-dive on the strongest topic
  evergreen    — a beginner/“start here” entry point for the strongest topic
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from app.services.analytics.engine import Analysis, GroupStat
from app.services.analytics.prediction import Prediction, predict
from app.services.analytics.records import PLATFORM_FORMATS, PLATFORMS

SHORT_FORMATS = {"Short", "Reel"}
LONG_FORMATS = {"Long-form"}
STATIC_FORMATS = {"Post"}

# (angle id, title template, hook template)
ANGLES: List[Tuple[str, str, str]] = [
    ("mistakes", "{N} {Topic} Mistakes I Wish I'd Fixed Sooner",
     "Mistake #2 cost me three months — and almost everyone is making it right now."),
    ("truth", "The Truth About {Topic} Nobody Tells You",
     "Everyone says {topic} is about X. After {posts} posts, here's what actually moved the needle."),
    ("system", "My Complete {Topic} System, Step by Step",
     "I used to wing {topic}. Now it takes me half the time — this is the exact system."),
    ("fast", "{Topic} in 60 Seconds (No Fluff)",
     "You don't need a 20-minute tutorial. Here's {topic} in the time it takes to read a comment."),
    ("before_after", "{Topic}: Before vs After",
     "Same shot. Same gear. Watch what changes when I fix {topic}."),
    ("ranked", "Every {Topic} Approach I've Tried — Ranked",
     "I've tried all of them so you don't have to. Number one surprised me."),
    ("beginner", "{Topic} for Beginners: Start Here",
     "If you're starting {topic} from zero, skip the rabbit hole — do these three things first."),
    ("budget", "{Topic} on a Budget — What Actually Matters",
     "You don't need the expensive version. Here's the 20% of {topic} that delivers 80% of the result."),
    ("behind", "What Really Goes Into {Topic} (Unfiltered)",
     "This is the part of {topic} that never makes the final cut."),
    ("secret", "The {Topic} Trick That Changed Everything",
     "One small change to my {topic} doubled my results — and it takes 30 seconds."),
    ("questions", "Your {Topic} Questions, Answered Honestly",
     "You asked about {topic} more than anything else last month — let's go through it."),
    ("day", "A Day of {Topic}: Start to Finish",
     "From the first coffee to the final export — here's a full day of {topic}."),
]

STRATEGY_ANGLES: Dict[str, List[str]] = {
    "double_down": ["system", "secret", "truth", "ranked"],
    "cross_post": ["fast", "before_after", "secret", "mistakes"],
    "remix": ["fast", "before_after", "secret"],
    "revive": ["truth", "mistakes", "before_after", "budget"],
    "series": ["system", "day", "behind"],
    "evergreen": ["beginner", "budget", "questions"],
}


@dataclass
class Idea:
    id: str
    title: str
    hook: str
    outline: List[str]
    platform: str
    content_type: str
    topics: List[str]
    strategy: str
    rationale: str
    recommended_slot: Optional[Dict[str, Any]]
    prediction: Dict[str, Any]
    confidence_score: float
    description: str = ""
    source: str = "analytics"
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trend_id: Optional[str] = None
    kit: Dict[str, Any] = field(default_factory=dict)      # production kit (shot list, thumbnail, caption, checklist…)
    enrichment_status: Optional[str] = None                # None | queued | done | failed | skipped

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
BRANDS = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "davinci": "DaVinci",
          "iphone": "iPhone", "ipad": "iPad", "macbook": "MacBook", "premiere": "Premiere", "sony": "Sony",
          "b-roll": "B-Roll", "q&a": "Q&A", "gopro": "GoPro", "dji": "DJI", "capcut": "CapCut", "ai": "AI"}


def _titleize(s: str) -> str:
    small = {"and", "or", "of", "the", "a", "in", "on", "for", "to", "vs"}
    out = []
    for i, w in enumerate(s.split()):
        if w.lower() in BRANDS:
            out.append(BRANDS[w.lower()])
        elif i == 0 or w not in small:
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out)


def _pick(seq: Sequence[Any], *keys: Any) -> Any:
    h = hashlib.sha256("|".join(str(k) for k in keys).encode()).hexdigest()
    return seq[int(h[:8], 16) % len(seq)]


def build_outline(content_type: str, topic: str, angle: str, posts: int) -> List[str]:
    t = topic
    if content_type in SHORT_FORMATS:
        return [
            f"0–3s — Hook on screen + spoken: the {t} promise (pattern interrupt, no intro).",
            f"3–12s — Show the problem with {t} visually (before / wrong way).",
            f"12–25s — The fix: one concrete {t} step, shown not told. Text overlay the key number.",
            "25–35s — Proof / result (after shot, metric, reaction).",
            "Last 3s — Loop-friendly ending + CTA: “Save this for your next shoot” / follow for part 2.",
        ]
    if content_type in LONG_FORMATS:
        return [
            f"Cold open (0:00–0:30) — the {t} result first, then the promise of the video.",
            f"Context (0:30–2:00) — why {t} matters for creators; what you tried before ({posts} posts of evidence).",
            f"Section 1 — Foundations: the 2–3 {t} decisions that matter most.",
            f"Section 2 — Walkthrough: step-by-step {t} process with on-screen examples.",
            f"Section 3 — Mistakes & fixes: what went wrong, what you'd do differently.",
            "Result & recap — before/after comparison, key numbers on screen.",
            "CTA — link the related Short/Reel; ask one specific question for comments.",
        ]
    # Static post / carousel
    return [
        f"Slide 1 (cover) — bold claim about {t} + 'swipe' cue.",
        f"Slide 2 — the common {t} mistake (relatable screenshot / photo).",
        f"Slides 3–6 — one {t} tip per slide, big headline + one-line why.",
        "Slide 7 — before/after or results.",
        "Slide 8 — recap + CTA: save / share / comment your setup.",
    ]


def angle_for(strategy: str, *keys: Any, used: set) -> Tuple[str, str, str]:
    candidates = [a for a in ANGLES if a[0] in STRATEGY_ANGLES.get(strategy, [])] or ANGLES
    fresh = [a for a in candidates if a[0] not in used] or candidates
    return _pick(fresh, strategy, *keys)


def render(template: str, topic: str, posts: int, n: int = 5) -> str:
    return (template
            .replace("{Topic}", _titleize(topic))
            .replace("{topic}", topic)
            .replace("{posts}", str(posts))
            .replace("{N}", str(n)))


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------
class IdeaGenerator:
    def __init__(self, analysis: Analysis, calibration_lookup=None, seed: int = 0):
        """
        calibration_lookup(platform, content_type) -> (factor, samples)
        """
        self.a = analysis
        self.cal = calibration_lookup or (lambda p, c: (1.0, 0))
        self.seed = seed
        self.patterns = analysis.patterns()
        self.topics: List[GroupStat] = [GroupStat(**t) for t in self.patterns["topics"]]
        self.formats: List[GroupStat] = [GroupStat(**f) for f in self.patterns["formats"]]

    # ---- helpers -------------------------------------------------------
    def best_format(self, platform: str) -> str:
        for f in self.formats:
            if f.key.startswith(platform + ":"):
                return f.key.split(":", 1)[1]
        return PLATFORM_FORMATS[platform][0]

    def format_lift(self, platform: str, content_type: str) -> float:
        for f in self.formats:
            if f.key == f"{platform}:{content_type}":
                return f.lift
        return 1.0

    def topic_platform(self, topic: GroupStat) -> str:
        """Platform where this topic performed best (by relative performance)."""
        best, best_val = None, -1.0
        for pl in PLATFORMS:
            members = [p for p in self.a.posts if p.platform == pl and topic.key in p.topics]
            if not members:
                continue
            val = sum(self.a.rel[p.id] for p in members) / len(members)
            if val > best_val:
                best, best_val = pl, val
        return best or PLATFORMS[0]

    def other(self, platform: str) -> str:
        return "Instagram" if platform == "YouTube" else "YouTube"

    def slot(self, platform: str, rank: int = 0) -> Optional[Dict[str, Any]]:
        slots = self.a.best_slots(platform, limit=3)
        if not slots:
            return None
        return slots[min(rank, len(slots) - 1)]

    def winners(self) -> List[GroupStat]:
        return [t for t in self.topics if t.lift >= 1.05] or self.topics[:3]

    def losers(self) -> List[GroupStat]:
        return [t for t in self.topics if t.lift <= 0.9]

    # ---- candidate plan -----------------------------------------------
    def candidates(self, n: int) -> List[Dict[str, Any]]:
        """Ordered (strategy, topic, platform, content_type) plan, diversified."""
        plan: List[Dict[str, Any]] = []
        winners = self.winners()
        losers = self.losers()
        if not self.topics:
            # No recurring topics yet: fall back to generic creator topics on best formats
            for i, pl in enumerate(PLATFORMS):
                plan.append({"strategy": "evergreen", "topic": None, "platform": pl, "content_type": self.best_format(pl)})
            return plan[:n]

        rot = self.seed
        used: set = set()

        def key(topic: Optional[GroupStat], platform: str, ct: str) -> Tuple[str, str, str]:
            return (topic.key if topic else "", platform, ct)

        def add(strategy: str, topic: Optional[GroupStat], platform: str, ct: str, **extra) -> None:
            k = key(topic, platform, ct)
            if k in used:
                return
            used.add(k)
            plan.append({"strategy": strategy, "topic": topic, "platform": platform, "content_type": ct, **extra})

        def w(i: int) -> GroupStat:
            return winners[(i + rot) % len(winners)]

        def fresh_winner(start: int, platform: Optional[str] = None, ct: Optional[str] = None) -> GroupStat:
            """Next winner (from *start*) not already used for this platform/format."""
            for j in range(len(winners)):
                t = w(start + j)
                pl = platform or self.topic_platform(t)
                c = ct or self.best_format(pl)
                if key(t, pl, c) not in used:
                    return t
            return w(start)

        t0 = fresh_winner(0)
        p0 = self.topic_platform(t0)
        add("double_down", t0, p0, self.best_format(p0))

        t1 = fresh_winner(1)
        p1 = self.other(self.topic_platform(t1))
        add("cross_post", t1, p1, self.best_format(p1))

        # remix: a top long/static piece → short-form on the same platform; prefer a topic not used yet
        ranked_long = [p for p in sorted(self.a.posts, key=lambda x: -self.a.rel[x.id]) if p.content_type in LONG_FORMATS | STATIC_FORMATS]
        for src in ranked_long[rot:] + ranked_long[:rot]:
            short_ct = "Short" if src.platform == "YouTube" else "Reel"
            topic = next((t for t in self.topics if t.key in src.topics), None)
            if topic is None or key(topic, src.platform, short_ct) in used:
                continue
            add("remix", topic, src.platform, short_ct, source_post=src)
            break

        if losers:
            tl = losers[(0 + rot) % len(losers)]
            pl = self.topic_platform(tl)
            add("revive", tl, pl, self.best_format(pl))

        t2 = fresh_winner(2, "YouTube", "Long-form")
        add("series", t2, "YouTube", "Long-form")

        t3 = fresh_winner(3)
        p3 = self.topic_platform(t3)
        add("evergreen", t3, p3, "Post" if p3 == "Instagram" else "Long-form")

        # Fill up with more winners on best formats if more are requested
        i = 4
        while len(plan) < n and i < len(winners) + 8:
            t = w(i)
            pl = self.topic_platform(t) if i % 2 == 0 else self.other(self.topic_platform(t))
            add("double_down" if i % 2 == 0 else "cross_post", t, pl, self.best_format(pl))
            i += 1
        return plan[:n]

    # ---- render one idea ----------------------------------------------
    def make(self, c: Dict[str, Any], used_angles: set, rank: int) -> Idea:
        topic: Optional[GroupStat] = c["topic"]
        platform, ct, strategy = c["platform"], c["content_type"], c["strategy"]
        topic_label = topic.label if topic else "content creation"
        topic_keys = [topic.key] if topic else []
        posts = topic.posts if topic else 0

        angle_id, title_t, hook_t = angle_for(strategy, topic_label, platform, ct, self.seed, used=used_angles)
        used_angles.add(angle_id)
        title = render(title_t, topic_label, posts)
        hook = render(hook_t, topic_label, posts)
        if ct == "Reel" or ct == "Short":
            title = title.replace(" (No Fluff)", "")
        if strategy == "series":
            title = f"{title} — Part 1"
        if strategy == "remix" and c.get("source_post") is not None:
            src = c["source_post"]
            title = f"{_titleize(topic_label)}: The 30-Second Version"
            hook = f"You watched “{src.title[:48]}” — here's the one thing to remember."

        slot = self.slot(platform, rank % 2)
        factor, samples = self.cal(platform, ct)
        pred: Prediction = predict(self.a, platform, ct, topic_keys, slot, factor, samples)

        fl = self.format_lift(platform, ct)
        bits = []
        if topic:
            bits.append(f"“{topic.label}” runs {topic.lift}x your typical post across {topic.posts} posts ({topic.confidence} confidence)")
        bits.append(f"{ct}s are {fl}x the {platform} median")
        if slot:
            bits.append(f"{slot['weekday_label']} {slot['hour_bucket']} slots lift results {slot['lift']}x")
        if factor != 1.0:
            bits.append(f"calibrated ×{factor:.2f} from {samples} reviewed predictions")
        strategy_text = {
            "double_down": "Double down on what already works.",
            "cross_post": "Carry a proven topic to the other platform's strongest format.",
            "revive": "Low-risk experiment: a weak topic with a high-contrast angle.",
            "remix": "Repurpose a top performer into short-form to reach new viewers.",
            "series": "Build a series to compound watch time and returning viewers.",
            "evergreen": "Evergreen entry point that keeps pulling search/discovery traffic.",
        }[strategy]
        rationale = f"{strategy_text} " + "; ".join(bits) + "."

        outline = build_outline(ct, topic_label, angle_id, posts)
        description = f"{strategy_text} Expected {pred.expected_views:,} views ({pred.views_low:,}–{pred.views_high:,})."

        return Idea(
            id=str(uuid4()),
            title=title,
            hook=hook,
            outline=outline,
            platform=platform,
            content_type=ct,
            topics=[topic_label] if topic else [],
            strategy=strategy,
            rationale=rationale,
            recommended_slot=slot,
            prediction=pred.to_dict(),
            confidence_score=pred.confidence,
            description=description,
        )

    def generate(self, n: int = 6) -> List[Idea]:
        used: set = set()
        ideas = [self.make(c, used, i) for i, c in enumerate(self.candidates(n))]
        # Make sure titles are unique within the batch
        seen: Dict[str, int] = {}
        for idea in ideas:
            k = idea.title.lower()
            if k in seen:
                seen[k] += 1
                idea.title = f"{idea.title} ({seen[k]})"
            else:
                seen[k] = 1
        return ideas
