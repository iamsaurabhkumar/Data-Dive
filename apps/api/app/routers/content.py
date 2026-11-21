import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.schemas import ContentPostSchema, FeedResponse, MetricsSchema, SummaryResponse, SyncRequest, SyncResponse
from app.services.aggregator import AggregatorService
from app.services.analytics.engine import Analysis
from app.services.mock_data import MOCK_NOW
from app.services.posts import ensure_creator_profile, load_posts, sort_posts

logger = logging.getLogger("datadive.content")
router = APIRouter(prefix="/api/content", tags=["content"])


async def _creator_id(user: dict, db: Optional[AsyncSession]) -> str:
    if get_settings().mock_mode or db is None:
        return user["sub"]
    return await ensure_creator_profile(db, user["sub"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    platform: Optional[str] = Query(None, description="Filter by platform: YouTube, Instagram"),
    content_type: Optional[str] = Query(None, description="Filter by type: Short, Long-form, Reel, Post"),
    sort_by: str = Query("published_at", description="Sort field: published_at, views, likes, comments"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(60, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    posts = await load_posts(db, await _creator_id(user, db))
    if platform and platform.lower() != "all":
        posts = [p for p in posts if p.platform.lower() == platform.lower()]
    if content_type and content_type.lower() != "all":
        posts = [p for p in posts if p.content_type.lower() == content_type.lower()]
    posts = sort_posts(posts, sort_by, sort_order)

    total = len(posts)
    start = (page - 1) * per_page
    page_items = posts[start:start + per_page]
    return FeedResponse(
        posts=[
            ContentPostSchema(
                id=p.id,
                platform=p.platform,
                external_post_id=p.external_post_id or p.id,
                title=p.title,
                content_type=p.content_type,
                thumbnail_url=p.thumbnail_url,
                published_at=p.published_at.isoformat() if p.published_at else None,
                metrics=MetricsSchema(
                    views=p.views, likes=p.likes, comments=p.comments,
                    watch_time_hours=p.watch_time_hours, shares=p.shares, saves=p.saves,
                ),
            )
            for p in page_items
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    settings = get_settings()
    posts = await load_posts(db, await _creator_id(user, db))
    ov = Analysis(posts, tz=settings.creator_timezone, now=MOCK_NOW if settings.mock_mode else None).overview()
    by_platform = {ps["platform"]: ps for ps in ov["platforms"]}
    return SummaryResponse(
        total_views=ov["total_views"],
        total_likes=ov["total_likes"],
        total_comments=ov["total_comments"],
        total_posts=ov["total_posts"],
        avg_views_per_post=ov["avg_views_per_post"],
        avg_engagement_rate=ov["avg_engagement_rate"],
        top_platform=ov["top_platform"] if ov["total_posts"] else "None",
        top_content_type=ov["top_content_type"] if ov["total_posts"] else "None",
        platform_breakdown={
            "youtube": {"posts": by_platform["YouTube"]["posts"], "views": by_platform["YouTube"]["total_views"]},
            "instagram": {"posts": by_platform["Instagram"]["posts"], "views": by_platform["Instagram"]["total_views"]},
        },
    )


@router.post("/sync", response_model=SyncResponse)
async def sync_content(
    request: SyncRequest,
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    settings = get_settings()
    if settings.mock_mode or db is None:
        return SyncResponse(success=True, posts_synced=60, message="Mock sync completed.")

    if not request.provider_token:
        # Supabase only exposes provider_token right after the OAuth redirect.
        return SyncResponse(
            success=False,
            posts_synced=0,
            message="No platform token in this session — sign in again to refresh the connection, then sync.",
        )

    youtube_token = request.provider_token if request.provider == "google" else None
    instagram_token = request.provider_token if request.provider == "facebook" else None

    try:
        creator_id = await ensure_creator_profile(db, user["sub"])
        stats = await AggregatorService(db, creator_id).sync_platform_data(youtube_token, instagram_token)
    except Exception:
        logger.exception("Platform sync failed for user %s", user.get("sub"))
        raise HTTPException(status_code=502, detail="Platform sync failed. Check the server logs for details.")

    total = stats["youtube_synced"] + stats["instagram_synced"]
    errors = stats.get("errors") or []
    return SyncResponse(
        success=not errors,
        posts_synced=total,
        message=f"Synced {total} posts (YT: {stats['youtube_synced']}, IG: {stats['instagram_synced']})"
                + (f". Problems: {'; '.join(errors)}" if errors else ""),
    )
