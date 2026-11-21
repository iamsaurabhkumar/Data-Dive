"""
"Generate Next Project" — one complete, production-ready project built from
the best current trend for this creator, grounded in their own analytics.

Output = an Idea (source="trend", strategy="trend_jack") with:
  title / hook / outline              — trend subject × creator's winning topic × format
  recommended slot + forecast         — same explainable model, plus a bounded `trend` lift
  kit                                 — shot list, thumbnail concept, caption, hashtags,
                                        per-Kanban-column checklist and the trend window
If no trend is relevant (or none exist) it falls back to the creator's strongest
analytics idea and says so, so the button always produces something useful.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from app.services.analytics.engine import Analysis
from app.services.analytics.ideas import BRANDS, Idea, IdeaGenerator, _titleize, build_outline
from app.services.analytics.prediction import predict
from app.services.analytics.records import PLATFORM_FORMATS
from app.services.analytics.trends import ScoredTrend, TrendRecord, score_trends

MIN_RELEVANT_SCORE = 0.25     # below this the "best" trend is not worth chasing for this creator
TREND_WINDOW_HOURS = 72

TITLE_TEMPLATES = [
    "I Tried {subject} — Honest {Topic} Verdict",
    "{subject}: What It Really Means for {Topic}",
    "Everyone's Doing {subject}. Here's the {Topic} Version That Works",
    "{subject} Changed My {Topic} Workflow (Tested)",
    "The {Topic} Take on {subject} Nobody Is Making",
]
HOOK_TEMPLATES = [
    "Everyone is talking about {subject_lc}. I tested it against my own {topic} setup — the result surprised me.",
    "{subject} is everywhere right now. Here's what actually matters if you care about {topic}.",
    "You've seen {subject_lc} all over your feed. Give me {seconds} seconds and I'll show you the {topic} angle no one covers.",
]


@dataclass
class NextProject:
    idea: Idea
    chosen: Optional[ScoredTrend]
    alternatives: List[ScoredTrend] = field(default_factory=list)
    trends_considered: int = 0
    fallback_reason: Optional[str] = None


def _pick(seq: Sequence[Any], *keys: Any) -> Any:
    h = hashlib.sha256("|".join(map(str, keys)).encode()).hexdigest()
    return seq[int(h[:8], 16) % len(seq)]


_EMOJI = re.compile(r"[^\w\s'&$%+.,:!?/-]", re.UNICODE)
# Clause starters that turn a headline into commentary: "X that looks like…", "X everyone is copying", "X goes viral"
_CLAUSE = re.compile(
    r"\s+(?:that|which|who|everyone|everybody|people|goes|went|is|are|was|were|just|finally|explained|"
    r"reaction|reacts?|first look|review|vs\.?|compilation)\b.*$", re.IGNORECASE)
_TRAILING_FILLER = re.compile(r"\s+(?:trend|trends|challenge|update|news)$", re.IGNORECASE)


def clean_subject(title: str, max_words: int = 6, max_len: int = 44) -> str:
    """Headline → short subject: "The 'invisible cut' transition everyone is copying" → "The 'invisible cut' transition"."""
    s = re.split(r"\s+[—–|]\s+|\s+-\s+|:\s+|\s*\(", title)[0]     # split *before* stripping punctuation
    s = re.sub(r"#\w+", "", s)
    s = _EMOJI.sub("", s)
    s = _CLAUSE.sub("", s)
    s = _TRAILING_FILLER.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .,:-!?")
    words = s.split(" ")
    if len(words) > max_words:
        s = " ".join(words[:max_words])
    if len(s) > max_len:
        s = s[:max_len].rsplit(" ", 1)[0]
    s = s or title[:max_len]
    first = s.split(" ", 1)[0]
    if first[:1].islower() and first[1:] == first[1:].lower() and first.lower() not in BRANDS:
        s = s[0].upper() + s[1:]                 # "analog desk" → "Analog desk", but keep "iPhone"
    return s


def _plain_word(w: str) -> bool:
    """A capitalised common word ("The", "Analog") — not a brand/acronym ("YouTube", "AI", "iPhone")."""
    return w[:1].isupper() and w[1:] == w[1:].lower() and w.lower() not in BRANDS


_SMALL = {"a", "an", "and", "or", "of", "the", "in", "on", "for", "to", "vs", "at", "by", "with"}


def title_case(subject: str) -> str:
    """Headline case that keeps brands/acronyms ("iPhone", "YouTube", "AI") and handles quotes ("'Invisible")."""
    out = []
    for i, w in enumerate(subject.split(" ")):
        core = w.strip("'\"“”‘’")
        if w.lower().strip("'\"") in BRANDS:
            lead = w[: len(w) - len(w.lstrip("'\"“”‘’"))]
            out.append(lead + BRANDS[w.lower().strip("'\"“”‘’")] + w[len(lead) + len(core):])
        elif any(ch.isupper() for ch in core[1:]) or core.isupper():
            out.append(w)                                   # camelCase / acronym: leave as-is
        elif i > 0 and core.lower() in _SMALL:
            out.append(w.lower())
        else:
            idx = next((j for j, ch in enumerate(w) if ch.isalpha()), None)
            out.append(w if idx is None else w[:idx] + w[idx].upper() + w[idx + 1:])
    return " ".join(out)


def topic_text(topic: str) -> str:
    return " ".join(BRANDS.get(w, w) for w in topic.split(" "))


def platform_for(trend: TrendRecord, analysis: Analysis) -> Tuple[str, str]:
    """Map the trend's source onto one of the creator's platforms + best format."""
    def best_format(platform: str) -> str:
        fmts = [f for f in analysis.format_stats() if f.key.startswith(platform + ":")]
        return fmts[0].key.split(":", 1)[1] if fmts else PLATFORM_FORMATS[platform][0]

    if trend.source == "youtube":
        return "YouTube", best_format("YouTube")
    if trend.source in ("instagram", "tiktok"):
        return "Instagram", "Reel"                      # vertical short-form trend → Reel
    # news / other: explain it where the creator is strongest
    leader = analysis.overview()["top_platform"] or "YouTube"
    if leader == "YouTube":
        return "YouTube", "Long-form"
    return "Instagram", best_format("Instagram")


def build_kit(platform: str, ct: str, subject: str, topic: str, trend: Optional[TrendRecord],
              slot: Optional[Dict[str, Any]], age_hours: Optional[float]) -> Dict[str, Any]:
    short = ct in ("Short", "Reel")
    shots = (
        ["Cold-open close-up reacting to the trend (0–2s)", f"Screen/phone capture of {subject_lc(subject)} in the wild",
         f"Your {topic} setup: the test", "Result / before-after reveal", "Face-to-camera CTA (loopable ending)"]
        if short else
        ["A-roll intro with the result on screen", f"B-roll: {subject_lc(subject)} examples (fair-use clips / screenshots)",
         f"Demo: applying it to your {topic} workflow", "Side-by-side comparison", "Talking-head verdict", "End screen: related video"]
    )
    words = [w for w in re.findall(r"[A-Za-z0-9']+", subject) if len(w) > 2][:3]
    thumb_text = " ".join(words).upper() or topic.upper()
    tags = [t for t in (trend.tags if trend else [])][:4] + [topic]
    hashtags = []
    for t in tags:
        h = "#" + re.sub(r"[^a-z0-9]", "", t.lower())
        if len(h) > 2 and h not in hashtags:
            hashtags.append(h)
    for h in (["#shorts"] if ct == "Short" else ["#reels", "#creatortips"] if ct == "Reel" else []):
        if h not in hashtags:
            hashtags.append(h)
    caption = (
        f"{subject} — but make it useful for {topic}. "
        f"{'Save this for your next shoot' if short else 'Full breakdown in the video'} and tell me what you'd test next 👇"
    )
    window = None
    if trend is not None:
        remaining = max(TREND_WINDOW_HOURS - (age_hours or 0), 12)
        window = {
            "publish_within_hours": int(remaining),
            "reason": f"Trend first seen {int(age_hours or 0)}h ago; trend attention typically fades within ~{TREND_WINDOW_HOURS}h.",
        }
    return {
        "shot_list": shots,
        "thumbnail": {
            "text": thumb_text,
            "concept": "Split frame: the trend on the left, your result on the right; face with a clear reaction; max 3 words."
                       if not short else "Cover frame = the most surprising result frame with 3-word overlay.",
        },
        "caption": caption,
        "hashtags": hashtags[:8],
        "checklist": {
            "idea": ["Confirm the trend is still climbing", "Decide your unique angle in one sentence"],
            "scripting": ["Write the first-line hook (provided)", "Cut the outline to the beats below", "Plan one on-screen number/claim you can prove"],
            "filming": [f"Shoot the shot list ({len(shots)} shots)", "Record a second take of the hook", "Capture the before/after proof"],
            "editing": ["Hook lands in the first 2 seconds" if short else "Result shown in the first 30 seconds",
                        "Thumbnail / cover with the 3-word text", "Captions + hashtags ready"],
            "published": ["Post inside the trend window" + (f" ({window['publish_within_hours']}h)" if window else ""),
                          "Pin a comment asking what to test next", "Link the post on the Kanban card and review after 3 days"],
        },
        "trend_window": window,
        "slot": slot,
    }


def subject_lc(subject: str) -> str:
    """Sentence-case the subject for use mid-sentence without breaking brands."""
    first = subject.split(" ", 1)[0]
    return subject[0].lower() + subject[1:] if subject and _plain_word(first) else subject


class NextProjectGenerator:
    def __init__(self, analysis: Analysis, trends: Sequence[TrendRecord],
                 calibration_lookup: Optional[Callable[[str, str], Tuple[float, int]]] = None, seed: int = 0):
        self.a = analysis
        self.trends = list(trends)
        self.cal = calibration_lookup or (lambda p, c: (1.0, 0))
        self.seed = seed

    def generate(self, exclude_trend_ids: Sequence[str] = (), platform: Optional[str] = None) -> NextProject:
        scored = score_trends(self.a, self.trends, exclude_ids=exclude_trend_ids)
        if platform:
            scored = [s for s in scored if platform_for(s.trend, self.a)[0] == platform] or scored
        relevant = [s for s in scored if s.score >= MIN_RELEVANT_SCORE and s.matched_topics]
        if not relevant:
            reason = "no_trends" if not scored else "no_relevant_trends"
            return NextProject(self._fallback(reason, platform), None, scored[:3], len(scored), reason)
        best = relevant[0]
        alternatives = [s for s in scored if s is not best][:3]
        return NextProject(self._from_trend(best), best, alternatives, len(scored))

    # ---- trend → project ------------------------------------------------
    def _from_trend(self, st: ScoredTrend) -> Idea:
        t = st.trend
        platform, ct = platform_for(t, self.a)
        topic_key = max(st.matched_topics, key=lambda k: self.a.topic_lift(k)[0])
        topic = topic_text(self.a.label(topic_key))
        subject = clean_subject(t.title)
        slot = (self.a.best_slots(platform, 1) or [None])[0]

        template = _pick(TITLE_TEMPLATES, t.id, self.seed)
        subj = title_case(subject)
        if not template.startswith("{subject}"):
            subj = re.sub(r"^(The|A|An) ", lambda m: m.group(1).lower() + " ", subj)   # "…Doing the 'Invisible Cut'…"
        title = template.format(subject=subj, Topic=_titleize(topic))
        if len(title) > 95:
            title = f"{title_case(subject)}: The {_titleize(topic)} Take"
        hook = _pick(HOOK_TEMPLATES, t.id, self.seed, "hook").format(
            subject=subject, subject_lc=subject_lc(subject), topic=topic, seconds=30 if ct in ("Short", "Reel") else 60)

        outline = build_outline(ct, topic, "trend", st.trend.views)
        context_beat = (f"Trend context — show {subject_lc(subject)} in 1–2 seconds (screenshot/clip) so viewers know why now."
                        if ct in ("Short", "Reel") else
                        f"Why now — {subject} ({t.views:,} views, {t.source}); 20–30 seconds max, then pivot to your angle.")
        outline.insert(1, context_beat)

        trend_lift = 1 + 0.2 * st.momentum * st.relevance
        factor, samples = self.cal(platform, ct)
        pred = predict(self.a, platform, ct, st.matched_topics, slot, factor, samples, extra_lifts={"trend": trend_lift})

        kit = build_kit(platform, ct, subject, topic, t, slot, st.age_hours)
        rationale = (
            f"“{subject}” is trending on {t.source} ({t.views:,} views, ~{int(t.views_per_hour):,}/h, {int(st.age_hours)}h old) "
            f"and overlaps your {', '.join('“' + l + '”' for l in st.matched_labels)} content, which runs {st.topic_fit:.2f}x your typical post. "
            f"{ct}s are your strongest {platform} format"
            + (f"; best slot {slot['weekday_label']} {slot['hour_bucket']} ({slot['lift']}x)" if slot else "")
            + f". Trend score {st.score:.2f} (relevance {st.relevance:.2f}, momentum {st.momentum:.2f}, freshness {st.freshness:.2f})."
        )
        return Idea(
            id=str(uuid4()), title=title, hook=hook, outline=outline, platform=platform, content_type=ct,
            topics=[topic], strategy="trend_jack", rationale=rationale, recommended_slot=slot,
            prediction=pred.to_dict(), confidence_score=pred.confidence,
            description=f"Trend-driven project: {subject}. Expected {pred.expected_views:,} views "
                        f"({pred.views_low:,}–{pred.views_high:,}).",
            source="trend", trend_id=t.id, kit=kit,
        )

    # ---- fallback ----------------------------------------------------------
    def _fallback(self, reason: str, platform: Optional[str]) -> Idea:
        ideas = IdeaGenerator(self.a, self.cal, seed=self.seed).generate(6)
        if platform:
            ideas = [i for i in ideas if i.platform == platform] or ideas
        idea = ideas[0]
        topic = idea.topics[0] if idea.topics else "content creation"
        idea.kit = build_kit(idea.platform, idea.content_type, idea.title, topic, None, idea.recommended_slot, None)
        note = ("No fresh trends are available yet" if reason == "no_trends"
                else "None of the current trends overlap your content")
        idea.rationale = f"{note}, so this project doubles down on your own strongest pattern. " + idea.rationale
        idea.strategy = "double_down" if idea.strategy == "trend_jack" else idea.strategy
        return idea
