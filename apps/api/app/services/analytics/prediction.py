"""
Explainable performance prediction for a planned piece of content.

    expected_views = format_baseline × topic_lift × time_lift × calibration

* format_baseline — median views of the creator's posts in (platform, format)
* topic_lift      — shrunk geometric mean of the relative performance of the
                    creator's posts sharing the idea's topics
* time_lift       — relative performance of the recommended posting slot
* calibration     — learned per (creator, platform, format) from past
                    prediction reviews (1.0 until the system has learned)

The range is a log-normal 1-sigma interval using the dispersion of the
creator's own history, so formats with wild variance get wide ranges.
Every factor is returned so the UI can explain the number.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.services.analytics.engine import LIFT_CEIL, LIFT_FLOOR, Analysis, confidence_for

MODEL_VERSION = "v1"


@dataclass
class Prediction:
    platform: str
    content_type: str
    expected_views: int
    views_low: int
    views_high: int
    expected_engagement_rate: float       # percent
    expected_engagement: int
    confidence: float                     # 0..1
    confidence_label: str
    factors: Dict[str, Any] = field(default_factory=dict)
    recommended_slot: Optional[Dict[str, Any]] = None
    model_version: str = MODEL_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def combined_topic_lift(analysis: Analysis, topics: Sequence[str]) -> tuple[float, int]:
    """Average log-lift across the idea's topics (so two 1.4x topics don't become 1.96x)."""
    logs: List[float] = []
    n_total = 0
    for t in topics:
        lift, n = analysis.topic_lift(t)
        if n == 0:
            continue
        logs.append(math.log(lift))
        n_total += n
    if not logs:
        return 1.0, 0
    lift = math.exp(sum(logs) / len(logs))
    return max(LIFT_FLOOR, min(LIFT_CEIL, lift)), n_total


def predict(
    analysis: Analysis,
    platform: str,
    content_type: str,
    topics: Sequence[str],
    slot: Optional[Dict[str, Any]] = None,
    calibration_factor: float = 1.0,
    calibration_samples: int = 0,
    extra_lifts: Optional[Dict[str, float]] = None,
) -> Prediction:
    """
    extra_lifts — named, bounded multipliers from outside the creator's history
    (e.g. {"trend": 1.12}). Each is clamped to [0.8, 1.25] and reported in `factors`
    so a review can later show whether the bet on the trend paid off.
    """
    baseline = analysis.baseline_views(platform, content_type)
    n_format = analysis.group_sample_size(platform, content_type)
    topic_lift, n_topic = combined_topic_lift(analysis, topics)

    weekday = slot.get("weekday") if slot else None
    bucket = slot.get("hour_bucket") if slot else None
    time_lift = analysis.time_lift(weekday, bucket) if slot else 1.0

    calibration = max(0.25, min(4.0, calibration_factor or 1.0))
    extras = {k: round(max(0.8, min(1.25, float(v))), 3) for k, v in (extra_lifts or {}).items()}
    expected = baseline * topic_lift * time_lift * calibration
    for v in extras.values():
        expected *= v

    sigma = analysis.dispersion(platform, content_type)
    # Less history → wider interval
    if n_format < 3:
        sigma *= 1.4
    low = expected * math.exp(-sigma)
    high = expected * math.exp(sigma)

    er = analysis.baseline_engagement_rate(platform, content_type)  # fraction
    # Topics that over-index on views usually over-index (a little) on engagement as well.
    er_adj = er * (1 + 0.25 * (topic_lift - 1))

    confidence = 0.30
    confidence += 0.30 * min(n_format / 8.0, 1.0)
    confidence += 0.20 * min(n_topic / 4.0, 1.0)
    confidence += 0.15 * min(calibration_samples / 5.0, 1.0)
    confidence -= 0.10 if sigma > 0.9 else 0.0
    confidence = round(max(0.1, min(0.95, confidence)), 2)

    return Prediction(
        platform=platform,
        content_type=content_type,
        expected_views=int(round(expected)),
        views_low=int(round(low)),
        views_high=int(round(high)),
        expected_engagement_rate=round(er_adj * 100, 2),
        expected_engagement=int(round(expected * er_adj)),
        confidence=confidence,
        confidence_label=confidence_for(n_format if n_topic == 0 else min(n_format, max(n_topic, 1) * 2)),
        factors={
            "format_baseline_views": int(round(baseline)),
            "format_samples": n_format,
            "topic_lift": round(topic_lift, 3),
            "topic_samples": n_topic,
            "time_lift": round(time_lift, 3),
            "calibration": round(calibration, 3),
            "calibration_samples": calibration_samples,
            "sigma": round(sigma, 3),
            "topics": list(topics),
            **({"extra_lifts": extras} if extras else {}),
        },
        recommended_slot=slot,
    )
