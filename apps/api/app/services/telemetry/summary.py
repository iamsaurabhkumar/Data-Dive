"""Pure aggregation over usage events + feedback → dashboard payload."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.services.telemetry.models import FeatureFeedback, UsageEvent
from app.services.telemetry.taxonomy import FEATURES, FUNNEL


def _p(values: List[float], q: float) -> Optional[int]:
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return int(values[idx])


def summarize(events: Sequence[UsageEvent], feedback: Sequence[FeatureFeedback], days: int,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    events = [e for e in events if e.ts >= since]
    feedback = [f for f in feedback if f.created_at >= since]

    usage = [e for e in events if e.name in ("feature_used", "api_call", "page_view")]
    sessions = {e.session_id for e in usage if e.session_id}
    creators = {e.creator_id for e in usage if e.creator_id}
    active_days = {e.ts.date() for e in usage}

    # per feature
    per: Dict[str, Dict[str, Any]] = {}
    for feat in FEATURES:
        fe = [e for e in events if e.feature == feat]
        if not fe:
            continue
        api = [e for e in fe if e.name == "api_call"]
        lat = [float(e.duration_ms) for e in api if e.duration_ms is not None]
        errors = sum(1 for e in api if (e.status or 0) >= 500)
        actions = Counter(e.action for e in fe if e.name in ("feature_used", "api_call") and e.action)
        per[feat] = {
            "feature": feat,
            "label": FEATURES[feat],
            "uses": sum(1 for e in fe if e.name in ("feature_used", "api_call")),
            "page_views": sum(1 for e in fe if e.name == "page_view"),
            "sessions": len({e.session_id for e in fe if e.session_id}),
            "creators": len({e.creator_id for e in fe if e.creator_id}),
            "last_used": max(e.ts for e in fe).isoformat(),
            "avg_latency_ms": int(statistics.mean(lat)) if lat else None,
            "p95_latency_ms": _p(lat, 0.95),
            "error_rate": round(errors / len(api), 3) if api else None,
            "time_on_page_s": int(sum((e.duration_ms or 0) for e in fe if e.name == "page_view") / 1000),
            "top_actions": [{"action": a, "count": c} for a, c in actions.most_common(5)],
        }

    # funnel
    funnel = []
    prev = None
    for label, feat, action in FUNNEL:
        n = sum(1 for e in events if e.feature == feat and e.action == action and e.name in ("feature_used", "api_call"))
        funnel.append({"step": label, "feature": feat, "action": action, "count": n,
                       "conversion": round(n / prev, 3) if prev else None})
        prev = n if n else prev

    # daily series
    daily: Dict[str, Counter] = defaultdict(Counter)
    for e in usage:
        daily[e.ts.date().isoformat()][e.feature] += 1
    series = [{"date": d, "total": sum(c.values()), **dict(c)} for d, c in sorted(daily.items())]

    # feedback
    fb_per: Dict[str, Dict[str, Any]] = {}
    for feat in FEATURES:
        fs = [f for f in feedback if f.feature == feat]
        if not fs:
            continue
        worth = Counter(f.worth_it for f in fs)
        fb_per[feat] = {
            "feature": feat,
            "label": FEATURES[feat],
            "responses": len(fs),
            "avg_rating": round(statistics.mean(f.rating for f in fs), 2),
            "worth_it": {"yes": worth.get("yes", 0), "somewhat": worth.get("somewhat", 0), "no": worth.get("no", 0)},
            "worth_score": round((worth.get("yes", 0) + 0.5 * worth.get("somewhat", 0)) / len(fs), 2),
        }
    comments = [
        {"feature": f.feature, "rating": f.rating, "worth_it": f.worth_it, "improvement": f.improvement,
         "created_at": f.created_at.isoformat(), "trigger": f.trigger}
        for f in sorted(feedback, key=lambda f: f.created_at, reverse=True) if f.improvement
    ][:25]

    ranked = sorted(per.values(), key=lambda x: -x["uses"])
    return {
        "days": days,
        "since": since.isoformat(),
        "totals": {
            "events": len(events),
            "uses": len([e for e in usage if e.name != "page_view"]),
            "sessions": len(sessions),
            "creators": len(creators),
            "active_days": len(active_days),
            "feedback_responses": len(feedback),
            "avg_rating": round(statistics.mean(f.rating for f in feedback), 2) if feedback else None,
        },
        "features": ranked,
        "most_used": ranked[0]["feature"] if ranked else None,
        "funnel": funnel,
        "daily": series,
        "feedback": sorted(fb_per.values(), key=lambda x: -x["responses"]),
        "comments": comments,
    }
