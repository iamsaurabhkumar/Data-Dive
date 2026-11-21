"""
Prediction review + learning loop.

When a Kanban card reaches "published" and is linked to the real post, we
compare the stored prediction against the latest metrics, produce a verdict
and concrete lessons, and update the creator's calibration factor for that
(platform, format). The calibration is an exponentially-weighted geometric
mean of actual/predicted ratios, so predictions drift towards reality
without over-reacting to a single viral post.
"""
from __future__ import annotations

import difflib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.services.analytics.engine import Analysis
from app.services.analytics.records import WEEKDAYS, PostRecord, bucket_hour_range

EWMA_ALPHA = 0.35                 # weight of the newest observation
CAL_FLOOR, CAL_CEIL = 0.25, 4.0   # sanity bounds for a calibration factor
RATIO_CLAMP = (0.2, 5.0)          # one review can move the factor at most this much
MATCH_THRESHOLD = 0.45            # title similarity needed for auto-linking
MIN_AGE_DAYS_FOR_REVIEW = 0.0     # callers may enforce a waiting period (e.g. 3 days)


@dataclass
class Calibration:
    creator_id: str
    platform: str
    content_type: str
    factor: float = 1.0
    samples: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    verdict: str                       # outperformed | on_target | underperformed
    views_ratio: float                 # actual / predicted
    abs_pct_error: float               # |actual - predicted| / predicted
    within_range: bool
    er_delta: float                    # actual ER - predicted ER (percentage points)
    predicted: Dict[str, Any]
    actual: Dict[str, Any]
    lessons: List[str]
    calibration_before: float
    calibration_after: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def update_calibration(cal: Optional[Calibration], creator_id: str, platform: str, content_type: str,
                       views_ratio: float) -> Calibration:
    ratio = max(RATIO_CLAMP[0], min(RATIO_CLAMP[1], views_ratio if views_ratio > 0 else RATIO_CLAMP[0]))
    if cal is None or cal.samples == 0:
        new_factor = ratio ** 0.5   # first observation: move half-way (in log space) towards it
        samples = 1
    else:
        new_factor = math.exp((1 - EWMA_ALPHA) * math.log(cal.factor) + EWMA_ALPHA * math.log(ratio))
        samples = cal.samples + 1
    new_factor = max(CAL_FLOOR, min(CAL_CEIL, new_factor))
    return Calibration(
        creator_id=creator_id,
        platform=platform,
        content_type=content_type,
        factor=round(new_factor, 4),
        samples=samples,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def review_prediction(
    prediction: Dict[str, Any],
    actual: PostRecord,
    analysis: Analysis,
    calibration: Optional[Calibration],
    creator_id: str,
    recommended_slot: Optional[Dict[str, Any]] = None,
    tz: str = "UTC",
) -> tuple[ReviewResult, Calibration]:
    expected = max(int(prediction.get("expected_views") or 0), 1)
    low = int(prediction.get("views_low") or 0)
    high = int(prediction.get("views_high") or 0)
    exp_er = float(prediction.get("expected_engagement_rate") or 0.0)

    ratio = actual.views / expected
    abs_err = abs(actual.views - expected) / expected
    within = low <= actual.views <= high if high > 0 else False
    if actual.views > high:
        verdict = "outperformed"
    elif actual.views < low:
        verdict = "underperformed"
    else:
        verdict = "on_target"
    actual_er = round(actual.engagement_rate * 100, 2)
    er_delta = round(actual_er - exp_er, 2)

    lessons: List[str] = []

    # Magnitude
    if verdict == "on_target":
        lessons.append(f"Prediction held: {actual.views:,} views landed inside the {low:,}–{high:,} range.")
    elif verdict == "outperformed":
        lessons.append(f"Beat the forecast by {(ratio - 1) * 100:.0f}% ({actual.views:,} vs {expected:,} expected) — this combination deserves a follow-up.")
    else:
        lessons.append(f"Missed the forecast by {(1 - ratio) * 100:.0f}% ({actual.views:,} vs {expected:,} expected).")

    # Timing
    if recommended_slot and actual.published_at:
        wd, hb = actual.weekday(tz), actual.hour_bucket(tz)
        rec_wd, rec_hb = recommended_slot.get("weekday"), recommended_slot.get("hour_bucket")
        if wd is not None and (wd != rec_wd or hb != rec_hb):
            actual_lift = analysis.time_lift(wd, hb)
            rec_lift = analysis.time_lift(rec_wd, rec_hb)
            lessons.append(
                f"Published {WEEKDAYS[wd]} {hb} ({bucket_hour_range(hb)}) instead of the recommended "
                f"{WEEKDAYS[rec_wd]} {rec_hb}; historical lift {actual_lift:.2f}x vs {rec_lift:.2f}x."
                + (" Timing likely cost reach." if actual_lift < rec_lift * 0.9 and verdict == "underperformed" else "")
            )
        elif wd is not None:
            lessons.append(f"Published in the recommended slot ({WEEKDAYS[wd]} {hb}).")

    # Engagement
    if er_delta >= 1.0:
        lessons.append(f"Engagement rate {actual_er}% beat the {exp_er}% forecast — the hook/topic resonated; keep this angle.")
    elif er_delta <= -1.0:
        lessons.append(f"Engagement rate {actual_er}% fell short of {exp_er}% — viewers arrived but did not interact; test a stronger CTA or a more specific hook.")

    # Topic evidence in the actual title
    primary = analysis.primary_topics(actual) or actual.topics
    if primary:
        parts = []
        for t in primary[:3]:
            lift, n = analysis.topic_lift(t)
            parts.append(f"“{analysis.label(t)}” {lift:.2f}x (n={n})")
        lessons.append("Topics detected in the published title: " + ", ".join(parts) + ".")

    # Calibration
    before = calibration.factor if calibration else 1.0
    new_cal = update_calibration(calibration, creator_id, actual.platform, actual.content_type, ratio)
    direction = "up" if new_cal.factor > before else "down" if new_cal.factor < before else "unchanged"
    lessons.append(
        f"Calibration for {actual.content_type} on {actual.platform} moved {direction} to ×{new_cal.factor:.2f} "
        f"({new_cal.samples} reviewed prediction{'s' if new_cal.samples != 1 else ''}); future forecasts will reflect it."
    )

    result = ReviewResult(
        verdict=verdict,
        views_ratio=round(ratio, 3),
        abs_pct_error=round(abs_err, 3),
        within_range=within,
        er_delta=er_delta,
        predicted={
            "views": expected, "views_low": low, "views_high": high,
            "engagement_rate": exp_er, "confidence": prediction.get("confidence"),
            "slot": recommended_slot,
        },
        actual={
            "post_id": actual.id,
            "title": actual.title,
            "views": actual.views,
            "likes": actual.likes,
            "comments": actual.comments,
            "shares": actual.shares,
            "saves": actual.saves,
            "engagement_rate": actual_er,
            "published_at": actual.published_at.isoformat() if actual.published_at else None,
            "weekday": WEEKDAYS[actual.weekday(tz)] if actual.weekday(tz) is not None else None,
            "hour_bucket": actual.hour_bucket(tz),
            "age_days": round(actual.age_days(analysis.now) or 0, 1),
        },
        lessons=lessons,
        calibration_before=round(before, 4),
        calibration_after=new_cal.factor,
    )
    return result, new_cal


def accuracy_summary(reviews: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate accuracy over stored reviews (dicts with views_ratio / abs_pct_error / within_range)."""
    if not reviews:
        return {"count": 0, "mape": None, "hit_rate": None, "bias": None, "trend": None}
    errs = [float(r["abs_pct_error"]) for r in reviews]
    ratios = [float(r["views_ratio"]) for r in reviews if float(r["views_ratio"]) > 0]
    hits = [bool(r["within_range"]) for r in reviews]
    bias = math.exp(sum(math.log(x) for x in ratios) / len(ratios)) if ratios else None
    trend = None
    if len(errs) >= 4:
        half = len(errs) // 2
        earlier, later = errs[:half], errs[half:]
        trend = round((sum(earlier) / len(earlier)) - (sum(later) / len(later)), 3)  # >0 = improving
    return {
        "count": len(reviews),
        "mape": round(sum(errs) / len(errs), 3),
        "hit_rate": round(sum(hits) / len(hits), 3),
        "bias": round(bias, 3) if bias else None,   # >1 = predictions too low, <1 = too high
        "trend": trend,
    }


def auto_match_post(
    posts: Sequence[PostRecord],
    title: str,
    platform: str,
    content_type: Optional[str],
    around: Optional[datetime],
    window_days: int = 10,
    exclude_ids: Sequence[str] = (),
) -> Optional[tuple[PostRecord, float]]:
    """Find the creator's post most likely to be the published version of a card."""
    best: Optional[tuple[PostRecord, float]] = None
    for p in posts:
        if p.platform != platform or p.id in exclude_ids:
            continue
        if around and p.published_at and abs((p.published_at - around).total_seconds()) > window_days * 86400:
            continue
        score = difflib.SequenceMatcher(None, title.lower(), p.title.lower()).ratio()
        if content_type and p.content_type == content_type:
            score += 0.1
        if best is None or score > best[1]:
            best = (p, score)
    if best and best[1] >= MATCH_THRESHOLD:
        return best
    return None
