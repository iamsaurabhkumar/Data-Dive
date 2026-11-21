"""
Trend records + scoring against a creator's own analytics.

score = 0.55 × relevance + 0.30 × momentum + 0.15 × freshness

* relevance — overlap between the trend's words/tags and the creator's recurring
  topics, weighted by how well those topics perform for *this* creator
* momentum  — view velocity (views/hour) normalised across the candidate set
* freshness — exponential decay with a 72 h time constant (trends are perishable)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.services.analytics.engine import Analysis
from app.services.analytics.records import parse_dt
from app.services.analytics.topics import tokenize

W_RELEVANCE, W_MOMENTUM, W_FRESHNESS = 0.55, 0.30, 0.15
FRESHNESS_TAU_HOURS = 72.0
MAX_TREND_AGE = timedelta(days=7)


@dataclass
class TrendRecord:
    id: str
    source: str                       # youtube | instagram | tiktok | news
    category: str
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    views: int = 0
    views_per_hour: float = 0.0

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "TrendRecord":
        meta = row.get("raw_metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        return cls(
            id=str(row["id"]),
            source=(row.get("source") or "youtube").lower(),
            category=row.get("category") or "",
            title=row.get("title") or "",
            description=row.get("description") or "",
            tags=[str(t) for t in (meta.get("tags") or [])][:10],
            url=row.get("external_url"),
            fetched_at=parse_dt(row.get("fetched_at")),
            views=int(meta.get("views") or meta.get("view_count") or 0),
            views_per_hour=float(meta.get("views_per_hour") or 0.0),
        )


@dataclass
class ScoredTrend:
    trend: TrendRecord
    score: float
    relevance: float
    momentum: float
    freshness: float
    matched_topics: List[str]          # topic keys (stems)
    matched_labels: List[str]          # display labels
    topic_fit: float                   # mean lift of matched topics
    age_hours: float

    def to_dict(self) -> Dict[str, Any]:
        t = asdict(self.trend)
        t["fetched_at"] = self.trend.fetched_at.isoformat() if self.trend.fetched_at else None
        return {
            "trend": t,
            "score": round(self.score, 3),
            "relevance": round(self.relevance, 3),
            "momentum": round(self.momentum, 3),
            "freshness": round(self.freshness, 3),
            "matched_topics": self.matched_labels,
            "topic_fit": round(self.topic_fit, 3),
            "age_hours": round(self.age_hours, 1),
        }


def _trend_tokens(t: TrendRecord) -> set:
    # Title, description and tags only — the platform *category* ("creator", "tech") is too coarse
    # and produced false matches against similarly named creator topics.
    text = " ".join([t.title, t.description[:200], " ".join(t.tags)])
    return set(tokenize(text))


def score_trends(analysis: Analysis, trends: Sequence[TrendRecord], now: Optional[datetime] = None,
                 exclude_ids: Sequence[str] = ()) -> List[ScoredTrend]:
    now = now or analysis.now
    candidates = [t for t in trends if t.id not in set(exclude_ids) and t.title.strip()]
    candidates = [t for t in candidates if not t.fetched_at or now - t.fetched_at <= MAX_TREND_AGE]
    if not candidates:
        return []

    groups = analysis.topic_groups()
    topic_stats = {k: analysis.topic_lift(k) for k in groups}
    max_velocity = max((t.views_per_hour for t in candidates), default=0.0)

    scored: List[ScoredTrend] = []
    for t in candidates:
        tokens = _trend_tokens(t)
        matched = [k for k in groups if set(k.split(" ")) <= tokens]
        # keep the most specific matches only ("desk setup" over "desk")
        matched = [k for k in matched if not any(k != o and set(k.split(" ")) < set(o.split(" ")) for o in matched)]
        if matched:
            fit = sum(topic_stats[k][0] for k in matched) / len(matched)
            relevance = min(1.0, 0.35 + 0.2 * len(matched)) * min(fit, 1.6) / 1.6
        else:
            fit = 1.0
            relevance = 0.08
        momentum = (math.log10(1 + t.views_per_hour) / math.log10(1 + max_velocity)) if max_velocity > 0 else 0.0
        age_h = max((now - t.fetched_at).total_seconds() / 3600.0, 0.0) if t.fetched_at else 24.0
        freshness = math.exp(-age_h / FRESHNESS_TAU_HOURS)
        score = W_RELEVANCE * relevance + W_MOMENTUM * momentum + W_FRESHNESS * freshness
        scored.append(ScoredTrend(t, score, relevance, momentum, freshness, matched,
                                  [analysis.label(k) for k in matched], fit, age_h))
    scored.sort(key=lambda s: (-s.score, s.trend.id))
    return scored


# --------------------------------------------------------------------------
# Deterministic demo trends (mock mode). Niche matches the mock creator.
# --------------------------------------------------------------------------
_MOCK_TRENDS = [
    ("mt-01", "youtube", "tech", "iPhone 17 Pro cinematic mode — real filmmaker camera test",
     ["iphone", "camera", "cinematic", "filmmaking"], 2_400_000, 41_000, 6),
    ("mt-02", "tiktok", "creator", "The 'invisible cut' transition everyone is copying",
     ["transitions", "editing", "capcut", "reels"], 5_100_000, 88_000, 14),
    ("mt-03", "youtube", "software", "DaVinci Resolve 20 AI editing features first look",
     ["davinci", "editing", "ai", "color grade"], 910_000, 15_500, 20),
    ("mt-04", "instagram", "lifestyle", "Analog desk setup trend — no screens, just notebooks",
     ["desk setup", "aesthetic", "minimal", "workspace"], 650_000, 9_800, 30),
    ("mt-05", "news", "industry", "YouTube expands Shorts to 3 minutes — creators react",
     ["youtube", "shorts", "algorithm", "creators"], 300_000, 4_200, 40),
    ("mt-06", "youtube", "gaming", "Speedrun world record reaction compilation",
     ["gaming", "speedrun", "reaction"], 3_800_000, 95_000, 10),
    ("mt-07", "instagram", "tech", "$30 lighting hacks that look like a $3000 studio",
     ["lighting", "budget", "studio", "hacks"], 1_200_000, 22_000, 26),
    ("mt-08", "tiktok", "food", "Cloud bread 2.0 recipe goes viral",
     ["recipe", "baking", "viral"], 7_000_000, 120_000, 8),
]


def mock_trends(now: datetime) -> List[TrendRecord]:
    return [
        TrendRecord(id=tid, source=src, category=cat, title=title, tags=tags,
                    url=f"https://example.com/trend/{tid}", fetched_at=now - timedelta(hours=age),
                    views=views, views_per_hour=float(vph), description="")
        for tid, src, cat, title, tags, views, vph, age in _MOCK_TRENDS
    ]
