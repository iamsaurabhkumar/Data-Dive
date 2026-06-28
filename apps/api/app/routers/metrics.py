from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from collections import defaultdict
from datetime import datetime

from app.dependencies import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.content import ContentPost
from app.models.metric import MetricSnapshot
from app.schemas import InsightsResponse, WhatWorksSchema, PerformanceDataSchema

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if settings.mock_mode:
        # Return mock insights
        return InsightsResponse(
            what_works=WhatWorksSchema(
                top_content_type="Reel",
                top_platform="Instagram",
                recommendation_text="Your Instagram Reels are driving 2.5x more engagement than average. Consider doubling down on short-form video content on Instagram next week."
            ),
            performance_data=[
                PerformanceDataSchema(date="Mon", youtube_views=1200, instagram_views=3000),
                PerformanceDataSchema(date="Tue", youtube_views=1500, instagram_views=3500),
                PerformanceDataSchema(date="Wed", youtube_views=1800, instagram_views=3200),
                PerformanceDataSchema(date="Thu", youtube_views=2100, instagram_views=4000),
                PerformanceDataSchema(date="Fri", youtube_views=2500, instagram_views=4500),
                PerformanceDataSchema(date="Sat", youtube_views=3000, instagram_views=5500),
                PerformanceDataSchema(date="Sun", youtube_views=3200, instagram_views=6000),
            ]
        )

    # Real DB Fetch
    stmt = select(ContentPost).where(ContentPost.creator_id == user["sub"])
    result = await db.execute(stmt)
    posts = result.scalars().all()

    if not posts:
        return InsightsResponse(
            what_works=WhatWorksSchema(
                top_content_type="N/A",
                top_platform="N/A",
                recommendation_text="Not enough data yet. Try syncing some posts!"
            ),
            performance_data=[]
        )

    content_type_engagement = defaultdict(list)
    platform_views = defaultdict(int)
    
    # Very naive time-series grouping by day of week
    daily_views = defaultdict(lambda: {"youtube": 0, "instagram": 0})

    for p in posts:
        m_stmt = select(MetricSnapshot).where(MetricSnapshot.post_id == p.id).order_by(desc(MetricSnapshot.captured_at)).limit(1)
        snapshot = (await db.execute(m_stmt)).scalar_one_or_none()
        
        if not snapshot:
            continue
            
        engagement = snapshot.likes + snapshot.comments + snapshot.shares + snapshot.saves
        views = snapshot.views
        
        if views > 0:
            rate = engagement / views
            content_type_engagement[p.content_type].append(rate)
            
        platform_views[p.platform] += views
        
        if p.published_at:
            day_name = p.published_at.strftime("%a")
            if p.platform == "YouTube":
                daily_views[day_name]["youtube"] += views
            else:
                daily_views[day_name]["instagram"] += views

    # What Works Logic
    best_type = "N/A"
    best_rate = 0.0
    for c_type, rates in content_type_engagement.items():
        avg = sum(rates) / len(rates)
        if avg > best_rate:
            best_rate = avg
            best_type = c_type
            
    best_platform = "YouTube" if platform_views["YouTube"] >= platform_views["Instagram"] else "Instagram"
    
    if best_type != "N/A":
        rec_text = f"Your {best_type}s are driving the highest engagement rate ({round(best_rate*100, 1)}%). You should focus on creating more {best_type}s for {best_platform}."
    else:
        rec_text = "Not enough engagement data to make a recommendation."

    # Performance Data formatting
    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    perf_data = []
    for day in days_order:
        data = daily_views.get(day, {"youtube": 0, "instagram": 0})
        perf_data.append(PerformanceDataSchema(
            date=day,
            youtube_views=data["youtube"],
            instagram_views=data["instagram"]
        ))

    return InsightsResponse(
        what_works=WhatWorksSchema(
            top_content_type=best_type,
            top_platform=best_platform,
            recommendation_text=rec_text
        ),
        performance_data=perf_data
    )
