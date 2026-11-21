import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.content import ContentPost
from app.models.metric import MetricSnapshot
from app.models.creator import CreatorProfile
from app.services.youtube import YouTubeService
from app.services.instagram import InstagramService

logger = logging.getLogger("datadive.aggregator")


class AggregatorService:
    """Service to fetch data from all connected platforms and store it in the database."""

    def __init__(self, db: AsyncSession, creator_id: str):
        self.db = db
        self.creator_id = creator_id

    async def sync_platform_data(self, youtube_token: str = None, instagram_token: str = None) -> Dict[str, int]:
        """Fetches data from platforms and upserts into database."""
        # Ensure CreatorProfile exists to satisfy foreign key constraints
        stmt = select(CreatorProfile).where(CreatorProfile.id == self.creator_id)
        result = await self.db.execute(stmt)
        if not result.scalar_one_or_none():
            profile = CreatorProfile(id=self.creator_id, user_id=self.creator_id)
            self.db.add(profile)
            await self.db.commit()

        stats: Dict[str, Any] = {"youtube_synced": 0, "instagram_synced": 0, "errors": []}

        # 1. Sync YouTube — google-api-python-client is synchronous, so keep it off the event loop
        if youtube_token:
            try:
                yt_posts = await asyncio.to_thread(YouTubeService(youtube_token).fetch_recent_videos)
                await self._upsert_posts(yt_posts)
                stats["youtube_synced"] = len(yt_posts)
            except Exception:
                logger.exception("YouTube sync failed for creator %s", self.creator_id)
                stats["errors"].append("YouTube sync failed")

        # 2. Sync Instagram
        if instagram_token:
            try:
                ig_posts = await InstagramService(instagram_token).fetch_recent_posts()
                await self._upsert_posts(ig_posts)
                stats["instagram_synced"] = len(ig_posts)
            except Exception:
                logger.exception("Instagram sync failed for creator %s", self.creator_id)
                stats["errors"].append("Instagram sync failed")

        return stats

    async def _upsert_posts(self, posts_data: List[Dict[str, Any]]):
        """Upserts a list of normalized posts into the database."""
        for p_data in posts_data:
            # Check if post exists
            stmt = select(ContentPost).where(
                ContentPost.platform == p_data["platform"],
                ContentPost.external_post_id == p_data["external_post_id"]
            )
            result = await self.db.execute(stmt)
            post = result.scalar_one_or_none()

            # Insert new post if not exists
            if not post:
                pub_at = p_data.get("published_at")
                if isinstance(pub_at, str):
                    try:
                        pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                    except ValueError:
                        pub_at = None

                post = ContentPost(
                    creator_id=self.creator_id,
                    platform=p_data["platform"],
                    external_post_id=p_data["external_post_id"],
                    title=p_data["title"],
                    content_type=p_data["content_type"],
                    thumbnail_url=p_data["thumbnail_url"],
                    published_at=pub_at
                )
                self.db.add(post)
                await self.db.flush() # flush to get post.id

            # Insert metric snapshot
            metrics = p_data["metrics"]
            snapshot = MetricSnapshot(
                post_id=post.id,
                views=metrics["views"],
                likes=metrics["likes"],
                comments=metrics["comments"],
                watch_time_hours=metrics["watch_time_hours"],
                shares=metrics["shares"],
                saves=metrics["saves"]
            )
            self.db.add(snapshot)
            
        await self.db.commit()
