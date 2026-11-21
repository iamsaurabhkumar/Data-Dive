"""
Analytics engine — cross-platform performance analysis and pattern detection.

Everything here is a pure function over ``list[PostRecord]``.

Normalization strategy
----------------------
Raw views are not comparable across platforms or formats (a Short routinely
gets 10x the views of a Long-form video). Every post therefore gets a
*relative performance* ratio against the median of its own
``(platform, content_type)`` group. Topic and posting-time lifts are computed
from those ratios, so they are (approximately) independent of format, and can
be multiplied together by the prediction model:

    expected_views = format_median × topic_lift × time_lift × calibration

Lifts are geometric means of the ratios, shrunk towards 1.0 for small
samples (Bayesian shrinkage with pseudo-count ``SHRINK_K``), so a single
lucky post cannot produce a 5x lift.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.analytics.records import (
    HOUR_BUCKETS,
    PLATFORM_FORMATS,
    PLATFORMS,
    WEEKDAYS,
    PostRecord,
    bucket_hour_range,
)
from app.services.analytics.topics import TopicLabels, extract_topics, tokenize

SHRINK_K = 2.0          # pseudo-observations pulling a lift towards 1.0
MIN_GROUP = 2           # minimum posts for a pattern to be reported
LIFT_FLOOR, LIFT_CEIL = 0.4, 3.0
FORMAT_LIFT_CEIL = 10.0


# --------------------------------------------------------------------------
# Result structures
# --------------------------------------------------------------------------
@dataclass
class GroupStat:
    key: str
    label: str
    posts: int
    avg_views: int
    median_views: int
    avg_engagement_rate: float
    lift: float                 # shrunk geometric-mean relative performance
    raw_lift: float             # un-shrunk, for transparency
    confidence: str             # low | medium | high
    platforms: List[str] = field(default_factory=list)
    example_titles: List[str] = field(default_factory=list)


@dataclass
class Finding:
    kind: str                   # platform | format | topic | timing | momentum | cadence
    headline: str
    detail: str
    confidence: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformSummary:
    platform: str
    posts: int
    total_views: int
    total_engagement: int
    avg_views: int
    median_views: int
    avg_engagement_rate: float
    watch_time_hours: float
    best_format: Optional[str]
    best_format_lift: float
    posts_last_30d: int
    posts_per_week: float
    momentum: float             # recent median views / prior median views (1.0 = flat)
    top_posts: List[Dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def confidence_for(n: int) -> str:
    if n >= 6:
        return "high"
    if n >= 3:
        return "medium"
    return "low"


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def shrunk_geo_mean(ratios: Sequence[float], k: float = SHRINK_K, cap: float = LIFT_CEIL) -> float:
    """Geometric mean of ratios shrunk towards 1.0 with k pseudo-observations."""
    logs = [math.log(r) for r in ratios if r > 0]
    if not logs:
        return 1.0
    lift = math.exp(sum(logs) / (len(logs) + k))
    return max(LIFT_FLOOR, min(cap, lift))


def geo_mean(ratios: Sequence[float]) -> float:
    logs = [math.log(r) for r in ratios if r > 0]
    return math.exp(sum(logs) / len(logs)) if logs else 1.0


def format_key(platform: str, content_type: str) -> str:
    return f"{platform}:{content_type}"


# --------------------------------------------------------------------------
# Core analysis
# --------------------------------------------------------------------------
class Analysis:
    """Computed once per request; exposes overview, patterns, and baselines."""

    def __init__(self, posts: Sequence[PostRecord], tz: str = "UTC", now: Optional[datetime] = None):
        self.posts: List[PostRecord] = [p for p in posts if p.platform in PLATFORMS]
        self.tz = tz
        self.now = now or datetime.now(timezone.utc)

        # Topic assignment (mutates record.topics)
        topic_lists, self.labels = extract_topics([p.title for p in self.posts])
        for p, topics in zip(self.posts, topic_lists):
            p.topics = topics

        # Baselines: median views per (platform, format) and per platform
        self.format_median: Dict[str, float] = {}
        self.platform_median: Dict[str, float] = {}
        by_format: Dict[str, List[int]] = defaultdict(list)
        by_platform: Dict[str, List[int]] = defaultdict(list)
        for p in self.posts:
            by_format[format_key(p.platform, p.content_type)].append(p.views)
            by_platform[p.platform].append(p.views)
        for k, v in by_format.items():
            self.format_median[k] = max(_median(v), 1.0)
        for k, v in by_platform.items():
            self.platform_median[k] = max(_median(v), 1.0)

        # Relative performance per post
        self.rel: Dict[str, float] = {}
        for p in self.posts:
            base = self.format_median.get(format_key(p.platform, p.content_type), 1.0)
            self.rel[p.id] = (p.views / base) if base > 0 else 1.0

    # ---- baselines ------------------------------------------------------
    def baseline_views(self, platform: str, content_type: str) -> float:
        """Median views for a format, falling back to the platform median."""
        key = format_key(platform, content_type)
        if key in self.format_median:
            return self.format_median[key]
        if platform in self.platform_median:
            return self.platform_median[platform]
        # No history for this platform at all — use the global median
        all_views = [p.views for p in self.posts]
        return max(_median(all_views), 1.0)

    def baseline_engagement_rate(self, platform: str, content_type: str) -> float:
        group = [p.engagement_rate for p in self.posts if p.platform == platform and p.content_type == content_type]
        if not group:
            group = [p.engagement_rate for p in self.posts if p.platform == platform]
        if not group:
            group = [p.engagement_rate for p in self.posts]
        return _mean(group)

    def dispersion(self, platform: str, content_type: str) -> float:
        """Std-dev of log(relative performance) for the format — drives prediction ranges."""
        group = [self.rel[p.id] for p in self.posts if p.platform == platform and p.content_type == content_type]
        if len(group) < 3:
            group = [self.rel[p.id] for p in self.posts if p.platform == platform]
        if len(group) < 3:
            group = list(self.rel.values())
        logs = [math.log(r) for r in group if r > 0]
        if len(logs) < 2:
            return 0.6
        return max(0.25, min(1.2, statistics.pstdev(logs)))

    def group_sample_size(self, platform: str, content_type: str) -> int:
        return sum(1 for p in self.posts if p.platform == platform and p.content_type == content_type)

    # ---- group statistics ----------------------------------------------
    def _group_stat(self, key: str, label: str, members: List[PostRecord]) -> GroupStat:
        ratios = [self.rel[p.id] for p in members]
        views = [p.views for p in members]
        return GroupStat(
            key=key,
            label=label,
            posts=len(members),
            avg_views=int(_mean(views)),
            median_views=int(_median(views)),
            avg_engagement_rate=round(_mean([p.engagement_rate for p in members]) * 100, 2),
            lift=round(shrunk_geo_mean(ratios), 3),
            raw_lift=round(geo_mean(ratios), 3),
            confidence=confidence_for(len(members)),
            platforms=sorted({p.platform for p in members}),
            example_titles=[p.title for p in sorted(members, key=lambda x: -self.rel[x.id])[:3]],
        )

    def format_stats(self) -> List[GroupStat]:
        """Formats are compared against their *platform* median (not their own)."""
        groups: Dict[str, List[PostRecord]] = defaultdict(list)
        for p in self.posts:
            groups[format_key(p.platform, p.content_type)].append(p)
        out = []
        for key, members in groups.items():
            platform, ct = key.split(":", 1)
            base = self.platform_median.get(platform, 1.0)
            ratios = [p.views / base for p in members if base > 0]
            stat = self._group_stat(key, f"{ct} on {platform}", members)
            # Formats legitimately differ by >3x, so the display cap is wider here.
            # (Format lift is never multiplied into predictions — the format median is used directly.)
            stat.lift = round(shrunk_geo_mean(ratios, cap=FORMAT_LIFT_CEIL), 3)
            stat.raw_lift = round(geo_mean(ratios), 3)
            out.append(stat)
        out.sort(key=lambda s: -s.lift)
        return out

    def topic_groups(self, min_posts: int = MIN_GROUP) -> Dict[str, List[PostRecord]]:
        """Topic → posts, with redundant topics removed.

        When two topics cover exactly the same posts (e.g. the bigram "desk setup" and its
        fragments "desk" / "setup"), only the most specific one (longest) is kept.
        """
        groups: Dict[str, List[PostRecord]] = defaultdict(list)
        for p in self.posts:
            for t in p.topics:
                groups[t].append(p)
        groups = {t: m for t, m in groups.items() if len(m) >= min_posts}
        by_members: Dict[frozenset, str] = {}
        for t in sorted(groups, key=lambda x: (-len(x.split(" ")), -len(x), x)):
            key = frozenset(p.id for p in groups[t])
            by_members.setdefault(key, t)
        keep = set(by_members.values())
        return {t: m for t, m in groups.items() if t in keep}

    def primary_topics(self, post: PostRecord) -> List[str]:
        """The post's topics after redundant fragments are collapsed (see topic_groups)."""
        keep = self.topic_groups()
        return [t for t in post.topics if t in keep]

    def normalize_topic(self, topic: str) -> str:
        """Map a user-entered/display topic ("Editing tips") onto the stemmed key ("edit tip")."""
        if any(topic in p.topics for p in self.posts):
            return topic
        return " ".join(tokenize(topic))

    def topic_stats(self, min_posts: int = MIN_GROUP) -> List[GroupStat]:
        groups = self.topic_groups(min_posts)
        out = [self._group_stat(t, self.labels.label(t), members) for t, members in groups.items()]
        # Rank by confidence-weighted lift so a 1.3x on 8 posts beats 1.35x on 2 posts
        out.sort(key=lambda s: -(math.log(s.lift) * math.sqrt(s.posts)))
        return out

    def topic_lift(self, topic: str) -> Tuple[float, int]:
        topic = self.normalize_topic(topic)
        members = [p for p in self.posts if topic in p.topics]
        if not members:
            return 1.0, 0
        return shrunk_geo_mean([self.rel[p.id] for p in members]), len(members)

    def weekday_stats(self) -> List[GroupStat]:
        groups: Dict[int, List[PostRecord]] = defaultdict(list)
        for p in self.posts:
            wd = p.weekday(self.tz)
            if wd is not None:
                groups[wd].append(p)
        return [self._group_stat(str(wd), WEEKDAYS[wd], members) for wd, members in sorted(groups.items())]

    def hour_bucket_stats(self) -> List[GroupStat]:
        groups: Dict[str, List[PostRecord]] = defaultdict(list)
        for p in self.posts:
            hb = p.hour_bucket(self.tz)
            if hb is not None:
                groups[hb].append(p)
        return [
            self._group_stat(b, f"{b} ({bucket_hour_range(b)})", groups[b])
            for b in HOUR_BUCKETS if b in groups
        ]

    def slot_stats(self, min_posts: int = MIN_GROUP) -> List[GroupStat]:
        """Weekday × hour-bucket combinations."""
        groups: Dict[Tuple[int, str], List[PostRecord]] = defaultdict(list)
        for p in self.posts:
            wd, hb = p.weekday(self.tz), p.hour_bucket(self.tz)
            if wd is not None and hb is not None:
                groups[(wd, hb)].append(p)
        out = [
            self._group_stat(f"{wd}:{hb}", f"{WEEKDAYS[wd]} {hb}", members)
            for (wd, hb), members in groups.items() if len(members) >= min_posts
        ]
        out.sort(key=lambda s: -(math.log(s.lift) * math.sqrt(s.posts)))
        return out

    def time_lift(self, weekday: Optional[int], bucket: Optional[str]) -> float:
        """Combined timing lift for a slot; falls back to weekday × bucket when the slot is sparse."""
        if weekday is None or bucket is None:
            return 1.0
        slot = [self.rel[p.id] for p in self.posts if p.weekday(self.tz) == weekday and p.hour_bucket(self.tz) == bucket]
        if len(slot) >= MIN_GROUP:
            return shrunk_geo_mean(slot)
        wd = [self.rel[p.id] for p in self.posts if p.weekday(self.tz) == weekday]
        hb = [self.rel[p.id] for p in self.posts if p.hour_bucket(self.tz) == bucket]
        lift = shrunk_geo_mean(wd) * shrunk_geo_mean(hb)
        return max(LIFT_FLOOR, min(LIFT_CEIL, lift))

    def best_slots(self, platform: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """Ranked posting slots (weekday + bucket) for a platform."""
        posts = [p for p in self.posts if platform is None or p.platform == platform]
        wd_ratios: Dict[int, List[float]] = defaultdict(list)
        hb_ratios: Dict[str, List[float]] = defaultdict(list)
        slot_ratios: Dict[Tuple[int, str], List[float]] = defaultdict(list)
        for p in posts:
            wd, hb = p.weekday(self.tz), p.hour_bucket(self.tz)
            if wd is None or hb is None:
                continue
            wd_ratios[wd].append(self.rel[p.id])
            hb_ratios[hb].append(self.rel[p.id])
            slot_ratios[(wd, hb)].append(self.rel[p.id])

        candidates = []
        for wd in range(7):
            for hb in HOUR_BUCKETS:
                n_slot = len(slot_ratios.get((wd, hb), []))
                if n_slot >= MIN_GROUP:
                    lift = shrunk_geo_mean(slot_ratios[(wd, hb)])
                    n = n_slot
                else:
                    if wd not in wd_ratios or hb not in hb_ratios:
                        continue
                    lift = max(LIFT_FLOOR, min(LIFT_CEIL, shrunk_geo_mean(wd_ratios[wd]) * shrunk_geo_mean(hb_ratios[hb])))
                    n = min(len(wd_ratios[wd]), len(hb_ratios[hb]))
                candidates.append({
                    "weekday": wd,
                    "weekday_label": WEEKDAYS[wd],
                    "hour_bucket": hb,
                    "hour_range": bucket_hour_range(hb),
                    "lift": round(lift, 3),
                    "posts": n,
                    "confidence": confidence_for(n),
                })
        candidates.sort(key=lambda c: -(math.log(c["lift"]) * math.sqrt(max(c["posts"], 1))))
        return candidates[:limit]

    # ---- platform overview ---------------------------------------------
    def platform_summary(self, platform: str) -> PlatformSummary:
        posts = [p for p in self.posts if p.platform == platform]
        views = [p.views for p in posts]
        cutoff_30 = self.now - timedelta(days=30)
        cutoff_60 = self.now - timedelta(days=60)
        recent = [p for p in posts if p.published_at and p.published_at >= cutoff_30]
        prior = [p for p in posts if p.published_at and cutoff_60 <= p.published_at < cutoff_30]

        dated = [p.published_at for p in posts if p.published_at]
        span_weeks = 0.0
        if len(dated) >= 2:
            span_weeks = max((max(dated) - min(dated)).total_seconds() / (7 * 86400), 1.0)
        posts_per_week = round(len(posts) / span_weeks, 2) if span_weeks else float(len(posts))

        # Momentum on format-normalized performance so a month of Shorts vs a month of
        # Long-form does not masquerade as growth/decline.
        rec_med = _median([self.rel[p.id] for p in recent])
        pri_med = _median([self.rel[p.id] for p in prior])
        momentum = round(rec_med / pri_med, 2) if rec_med and pri_med else 1.0

        fmt = [s for s in self.format_stats() if s.key.startswith(platform + ":")]
        best = fmt[0] if fmt else None

        top = sorted(posts, key=lambda p: -self.rel[p.id])[:3]
        return PlatformSummary(
            platform=platform,
            posts=len(posts),
            total_views=sum(views),
            total_engagement=sum(p.engagement for p in posts),
            avg_views=int(_mean(views)),
            median_views=int(_median(views)),
            avg_engagement_rate=round(_mean([p.engagement_rate for p in posts]) * 100, 2),
            watch_time_hours=round(sum(p.watch_time_hours for p in posts), 1),
            best_format=best.key.split(":", 1)[1] if best else None,
            best_format_lift=best.lift if best else 1.0,
            posts_last_30d=len(recent),
            posts_per_week=posts_per_week,
            momentum=momentum,
            top_posts=[
                {
                    "id": p.id,
                    "title": p.title,
                    "content_type": p.content_type,
                    "views": p.views,
                    "relative_performance": round(self.rel[p.id], 2),
                    "engagement_rate": round(p.engagement_rate * 100, 2),
                    "published_at": p.published_at.isoformat() if p.published_at else None,
                }
                for p in top
            ],
        )

    def overview(self) -> Dict[str, Any]:
        platforms = [self.platform_summary(pl) for pl in PLATFORMS]
        total_views = sum(ps.total_views for ps in platforms)
        total_eng = sum(ps.total_engagement for ps in platforms)
        total_posts = len(self.posts)

        # Which platform "wins" on a normalized basis: engagement rate + momentum + views/post z
        leader = None
        if platforms and total_posts:
            scored = []
            for ps in platforms:
                if ps.posts == 0:
                    continue
                score = (ps.avg_engagement_rate / max(max(x.avg_engagement_rate for x in platforms), 0.01)) \
                    + (ps.momentum / max(max(x.momentum for x in platforms), 0.01))
                scored.append((score, ps.platform))
            if scored:
                leader = max(scored)[1]

        type_counts: Dict[str, int] = defaultdict(int)
        for p in self.posts:
            type_counts[p.content_type] += 1
        fmt = self.format_stats()

        return {
            "total_posts": total_posts,
            "total_views": total_views,
            "total_likes": sum(p.likes for p in self.posts),
            "total_comments": sum(p.comments for p in self.posts),
            "total_engagement": total_eng,
            "avg_views_per_post": int(total_views / total_posts) if total_posts else 0,
            "avg_engagement_rate": round((total_eng / total_views * 100) if total_views else 0.0, 2),
            "top_platform": leader or ("YouTube" if not platforms else max(platforms, key=lambda x: x.total_views).platform),
            "top_content_type": fmt[0].key.split(":", 1)[1] if fmt else "None",
            "platforms": [asdict(ps) for ps in platforms],
            "content_type_counts": dict(type_counts),
        }

    # ---- patterns + findings -------------------------------------------
    def patterns(self) -> Dict[str, Any]:
        topics = self.topic_stats()
        formats = self.format_stats()
        weekdays = self.weekday_stats()
        hours = self.hour_bucket_stats()
        slots = self.slot_stats()
        return {
            "timezone": self.tz,
            "sample_size": len(self.posts),
            "topics": [asdict(t) for t in topics],
            "formats": [asdict(f) for f in formats],
            "weekdays": [asdict(w) for w in weekdays],
            "hour_buckets": [asdict(h) for h in hours],
            "slots": [asdict(s) for s in slots[:6]],
            "best_slots": {pl: self.best_slots(pl) for pl in PLATFORMS},
            "findings": [asdict(f) for f in self.findings(topics, formats, weekdays, hours)],
        }

    def findings(
        self,
        topics: Optional[List[GroupStat]] = None,
        formats: Optional[List[GroupStat]] = None,
        weekdays: Optional[List[GroupStat]] = None,
        hours: Optional[List[GroupStat]] = None,
    ) -> List[Finding]:
        topics = topics if topics is not None else self.topic_stats()
        formats = formats if formats is not None else self.format_stats()
        weekdays = weekdays if weekdays is not None else self.weekday_stats()
        hours = hours if hours is not None else self.hour_bucket_stats()
        out: List[Finding] = []

        if not self.posts:
            return [Finding("platform", "Not enough data yet", "Sync your platforms to start finding patterns.", "low")]

        # Platform comparison
        summaries = {pl: self.platform_summary(pl) for pl in PLATFORMS}
        active = [s for s in summaries.values() if s.posts > 0]
        if len(active) == 2:
            a, b = sorted(active, key=lambda s: -s.avg_engagement_rate)
            out.append(Finding(
                "platform",
                f"{a.platform} converts attention better ({a.avg_engagement_rate}% vs {b.avg_engagement_rate}% engagement)",
                f"{b.platform} still delivers {b.total_views:,} views across {b.posts} posts vs {a.total_views:,} on {a.platform}; "
                f"use {b.platform} for reach and {a.platform} for community.",
                confidence_for(min(a.posts, b.posts)),
                {"engagement_rate": {a.platform: a.avg_engagement_rate, b.platform: b.avg_engagement_rate},
                 "views": {a.platform: a.total_views, b.platform: b.total_views}},
            ))
        for s in active:
            if s.momentum >= 1.2 and s.posts_last_30d >= 2:
                out.append(Finding("momentum", f"{s.platform} is trending up ({s.momentum}x recent median views)",
                                   f"Median views in the last 30 days are {s.momentum}x the previous 30 days — keep the cadence.",
                                   confidence_for(s.posts_last_30d), {"momentum": s.momentum}))
            elif s.momentum <= 0.8 and s.posts_last_30d >= 2:
                out.append(Finding("momentum", f"{s.platform} is cooling off ({s.momentum}x recent median views)",
                                   "Recent posts are underperforming your previous month — revisit the topics below that work.",
                                   confidence_for(s.posts_last_30d), {"momentum": s.momentum}))

        # Formats per platform
        for pl in PLATFORMS:
            pf = [f for f in formats if f.key.startswith(pl + ":")]
            if len(pf) >= 2 and pf[0].lift > 1.15:
                best, rest = pf[0], pf[1]
                out.append(Finding(
                    "format",
                    f"{best.key.split(':',1)[1]}s outperform on {pl} ({best.lift}x the platform median)",
                    f"{best.posts} {best.key.split(':',1)[1]} posts average {best.avg_views:,} views vs {rest.avg_views:,} for "
                    f"{rest.key.split(':',1)[1]}; engagement rate {best.avg_engagement_rate}% vs {rest.avg_engagement_rate}%.",
                    best.confidence,
                    {"lift": best.lift, "posts": best.posts},
                ))

        # Topics
        winners = [t for t in topics if t.lift >= 1.15][:3]
        losers = [t for t in topics if t.lift <= 0.85][-2:]
        for t in winners:
            out.append(Finding(
                "topic",
                f"“{t.label}” content performs {t.lift}x your typical post",
                f"{t.posts} posts across {', '.join(t.platforms)}; e.g. “{t.example_titles[0]}”.",
                t.confidence,
                {"topic": t.label, "lift": t.lift, "posts": t.posts},
            ))
        for t in losers:
            out.append(Finding(
                "topic",
                f"“{t.label}” underperforms ({t.lift}x)",
                f"{t.posts} posts land below your format median — reframe with a stronger angle or pair with a winning topic.",
                t.confidence,
                {"topic": t.label, "lift": t.lift, "posts": t.posts},
            ))

        # Timing
        if weekdays:
            best_wd = max(weekdays, key=lambda w: math.log(w.lift) * math.sqrt(w.posts))
            if best_wd.lift > 1.1 and best_wd.posts >= MIN_GROUP:
                out.append(Finding(
                    "timing",
                    f"{best_wd.label} posts do {best_wd.lift}x better",
                    f"Across {best_wd.posts} posts published on {best_wd.label}s ({self.tz}).",
                    best_wd.confidence,
                    {"weekday": best_wd.label, "lift": best_wd.lift},
                ))
        if hours:
            best_hb = max(hours, key=lambda h: math.log(h.lift) * math.sqrt(h.posts))
            if best_hb.lift > 1.1 and best_hb.posts >= MIN_GROUP:
                out.append(Finding(
                    "timing",
                    f"Publishing in the {best_hb.key} ({bucket_hour_range(best_hb.key)}) lifts results {best_hb.lift}x",
                    f"{best_hb.posts} posts in this window vs the rest of the day.",
                    best_hb.confidence,
                    {"hour_bucket": best_hb.key, "lift": best_hb.lift},
                ))

        # Cadence
        for s in active:
            if s.posts_per_week < 0.75 and s.posts >= 4:
                out.append(Finding("cadence", f"{s.platform} cadence is low ({s.posts_per_week}/week)",
                                   "Consistency compounds — aim for at least one post per week per platform.",
                                   "medium", {"posts_per_week": s.posts_per_week}))
        return out

    # ---- misc -----------------------------------------------------------
    def label(self, topic: str) -> str:
        return self.labels.label(topic)

    def as_feed(self) -> List[Dict[str, Any]]:
        return [p.to_feed_dict() for p in self.posts]
