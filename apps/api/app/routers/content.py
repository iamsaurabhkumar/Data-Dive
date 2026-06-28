from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, asc

from app.dependencies import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.content import ContentPost
from app.models.metric import MetricSnapshot
from app.schemas import (
    FeedResponse,
    ContentPostSchema,
    MetricsSchema,
    SummaryResponse,
    SyncResponse,
)
from app.services.mock_data import get_mock_feed, get_mock_summary
from app.services.aggregator import AggregatorService

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    platform: Optional[str] = Query(None, description="Filter by platform: YouTube, Instagram"),
    content_type: Optional[str] = Query(None, description="Filter by type: Short, Long-form, Reel, Post"),
    sort_by: str = Query("published_at", description="Sort field: published_at, views, likes"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(60, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if settings.mock_mode:
        posts_data = get_mock_feed(platform=platform, content_type=content_type)
        reverse = sort_order == "desc"
        if sort_by in ("views", "likes", "comments"):
            posts_data.sort(key=lambda p: p["metrics"].get(sort_by, 0), reverse=reverse)
        else:
            posts_data.sort(key=lambda p: p.get("published_at", ""), reverse=reverse)

        start = (page - 1) * per_page
        end = start + per_page
        paginated = posts_data[start:end]

        posts = [
            ContentPostSchema(
                id=p.get("id", p["external_post_id"]),
                platform=p["platform"],
                external_post_id=p["external_post_id"],
                title=p["title"],
                content_type=p["content_type"],
                thumbnail_url=p.get("thumbnail_url"),
                published_at=p.get("published_at"),
                metrics=MetricsSchema(**p["metrics"]),
            )
            for p in paginated
        ]
        return FeedResponse(posts=posts, total=len(posts_data), page=page, per_page=per_page)

    # Real DB Fetch
    stmt = select(ContentPost).where(ContentPost.creator_id == user["sub"])
    
    if platform and platform != "All":
        stmt = stmt.where(ContentPost.platform == platform)
    if content_type and content_type != "All":
        stmt = stmt.where(ContentPost.content_type == content_type)

    # Note: Sorting by metrics requires a join. For simplicity in MVP, 
    # we'll fetch all and sort in memory since we only fetch latest posts per platform.
    result = await db.execute(stmt)
    db_posts = result.scalars().all()

    posts_data = []
    for p in db_posts:
        # Get latest metric snapshot
        m_stmt = select(MetricSnapshot).where(MetricSnapshot.post_id == p.id).order_by(desc(MetricSnapshot.captured_at)).limit(1)
        m_result = await db.execute(m_stmt)
        snapshot = m_result.scalar_one_or_none()
        
        if not snapshot:
            continue
            
        posts_data.append({
            "post": p,
            "metrics": snapshot
        })

    # Sort
    reverse = sort_order == "desc"
    if sort_by == "views":
        posts_data.sort(key=lambda x: x["metrics"].views, reverse=reverse)
    elif sort_by == "likes":
        posts_data.sort(key=lambda x: x["metrics"].likes, reverse=reverse)
    else:
        posts_data.sort(key=lambda x: str(x["post"].published_at), reverse=reverse)

    total = len(posts_data)
    start = (page - 1) * per_page
    paginated = posts_data[start:start + per_page]

    schema_posts = [
        ContentPostSchema(
            id=str(item["post"].id),
            platform=item["post"].platform,
            external_post_id=item["post"].external_post_id,
            title=item["post"].title,
            content_type=item["post"].content_type,
            thumbnail_url=item["post"].thumbnail_url,
            published_at=item["post"].published_at.isoformat() if item["post"].published_at else None,
            metrics=MetricsSchema(
                views=item["metrics"].views,
                likes=item["metrics"].likes,
                comments=item["metrics"].comments,
                watch_time_hours=item["metrics"].watch_time_hours,
                shares=item["metrics"].shares,
                saves=item["metrics"].saves
            ),
        )
        for item in paginated
    ]

    return FeedResponse(posts=schema_posts, total=total, page=page, per_page=per_page)


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if settings.mock_mode:
        return SummaryResponse(**get_mock_summary())

    # Calculate real summary from DB
    stmt = select(ContentPost).where(ContentPost.creator_id == user["sub"])
    result = await db.execute(stmt)
    posts = result.scalars().all()
    
    if not posts:
        return SummaryResponse(total_views=0, total_posts=0, avg_engagement_rate=0.0, top_platform="None")

    total_views = 0
    total_engagements = 0
    platform_counts = {"YouTube": 0, "Instagram": 0}
    
    for p in posts:
        m_stmt = select(MetricSnapshot).where(MetricSnapshot.post_id == p.id).order_by(desc(MetricSnapshot.captured_at)).limit(1)
        snapshot = (await db.execute(m_stmt)).scalar_one_or_none()
        
        if snapshot:
            total_views += snapshot.views
            total_engagements += (snapshot.likes + snapshot.comments + snapshot.shares + snapshot.saves)
            platform_counts[p.platform] += snapshot.views

    top_platform = "YouTube" if platform_counts["YouTube"] >= platform_counts["Instagram"] else "Instagram"
    avg_engagement_rate = (total_engagements / total_views * 100) if total_views > 0 else 0.0

    return SummaryResponse(
        total_views=total_views,
        total_posts=len(posts),
        avg_engagement_rate=round(avg_engagement_rate, 2),
        top_platform=top_platform
    )


@router.post("/sync", response_model=SyncResponse)
async def sync_content(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if settings.mock_mode:
        return SyncResponse(success=True, posts_synced=60, message="Mock sync completed.")

    # We extract the provider tokens from the Supabase user identity session
    # For now, we simulate grabbing the tokens from the JWT if passed, 
    # but normally we'd query the DB or Supabase admin API for the user's identities.
    
    # NOTE: Since the frontend passes the provider tokens to a connect endpoint or we fetch via Supabase API,
    # let's assume we have them here. (We need to actually implement token storage or retrieval).
    # To keep it simple for MVP, we assume the tokens were saved in creator_profiles or passed in headers.
    
    # In a real production setup, we query Supabase Auth for identities.
    # For MVP we will just return a placeholder message if tokens aren't available.
    
    try:
        # TODO: Fetch real tokens from user's identities via Supabase Admin API
        youtube_token = None 
        instagram_token = None
        
        aggregator = AggregatorService(db, user["sub"])
        stats = await aggregator.sync_platform_data(youtube_token, instagram_token)
        
        total_synced = stats["youtube_synced"] + stats["instagram_synced"]
        
        return SyncResponse(
            success=True,
            posts_synced=total_synced,
            message=f"Synced {total_synced} posts (YT: {stats['youtube_synced']}, IG: {stats['instagram_synced']})"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
