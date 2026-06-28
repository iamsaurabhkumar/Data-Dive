from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, List

from app.models.content import ContentPost
from app.models.metric import MetricSnapshot
from app.services.youtube import YouTubeService
from app.services.instagram import InstagramService

class AggregatorService:
    """Service to fetch data from all connected platforms and store it in the database."""

    def __init__(self, db: AsyncSession, creator_id: str):
        self.db = db
        self.creator_id = creator_id

    async def sync_platform_data(self, youtube_token: str = None, instagram_token: str = None) -> Dict[str, int]:
        """Fetches data from platforms and upserts into database."""
        stats = {"youtube_synced": 0, "instagram_synced": 0}

        # 1. Sync YouTube
        if youtube_token:
            try:
                # YouTube client is currently synchronous (google-api-python-client)
                # In a real app we'd run this in a thread pool, but for now we call it directly
                yt_service = YouTubeService(youtube_token)
                yt_posts = yt_service.fetch_recent_videos()
                await self._upsert_posts(yt_posts)
                stats["youtube_synced"] = len(yt_posts)
            except Exception as e:
                print(f"YouTube sync error: {e}")

        # 2. Sync Instagram
        if instagram_token:
            try:
                ig_service = InstagramService(instagram_token)
                ig_posts = await ig_service.fetch_recent_posts()
                await self._upsert_posts(ig_posts)
                stats["instagram_synced"] = len(ig_posts)
            except Exception as e:
                print(f"Instagram sync error: {e}")

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
                post = ContentPost(
                    creator_id=self.creator_id,
                    platform=p_data["platform"],
                    external_post_id=p_data["external_post_id"],
                    title=p_data["title"],
                    content_type=p_data["content_type"],
                    thumbnail_url=p_data["thumbnail_url"],
                    published_at=p_data["published_at"]
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
