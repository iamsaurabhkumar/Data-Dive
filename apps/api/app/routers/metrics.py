"""
Legacy insights endpoint kept for the existing /insights page.

It is now a thin view over the analytics engine (same numbers as
/api/analytics/*), so mock and DB modes agree and there is one
definition of engagement rate.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.schemas import InsightsResponse, PerformanceDataSchema, WhatWorksSchema
from app.services.analytics.engine import Analysis
from app.services.analytics.records import WEEKDAYS
from app.services.mock_data import MOCK_NOW
from app.services.posts import ensure_creator_profile, load_posts

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    settings = get_settings()
    creator_id = user["sub"] if (settings.mock_mode or db is None) else await ensure_creator_profile(db, user["sub"])
    posts = await load_posts(db, creator_id)

    if not posts:
        return InsightsResponse(
            what_works=WhatWorksSchema(top_content_type="N/A", top_platform="N/A",
                                       recommendation_text="Not enough data yet. Try syncing some posts!"),
            performance_data=[],
        )

    analysis = Analysis(posts, tz=settings.creator_timezone, now=MOCK_NOW if settings.mock_mode else None)
    formats = analysis.format_stats()
    best = formats[0]
    platform, ct = best.key.split(":", 1)
    findings = analysis.findings()
    # Detail must describe the same platform as the headline (previously it took the first format finding of any platform)
    lead = next((f for f in findings if f.kind == "format" and f.headline.endswith(f"on {platform} ({best.lift}x the platform median)")), None) \
        or next((f for f in findings if f.kind == "format" and f" on {platform} " in f.headline), None)
    rec = (
        f"{ct}s on {platform} run {best.lift}x the platform median with a {best.avg_engagement_rate}% engagement rate "
        f"across {best.posts} posts ({best.confidence} confidence)."
        + (f" {lead.detail}" if lead else "")
    )

    # Views by publish weekday (what the old chart actually showed, now labelled honestly)
    buckets = {d: {"youtube": 0, "instagram": 0} for d in WEEKDAYS}
    for p in posts:
        wd = p.weekday(settings.creator_timezone)
        if wd is None:
            continue
        buckets[WEEKDAYS[wd]]["youtube" if p.platform == "YouTube" else "instagram"] += p.views

    return InsightsResponse(
        what_works=WhatWorksSchema(top_content_type=ct, top_platform=platform, recommendation_text=rec),
        performance_data=[
            PerformanceDataSchema(date=d, youtube_views=v["youtube"], instagram_views=v["instagram"])
            for d, v in buckets.items()
        ],
    )
