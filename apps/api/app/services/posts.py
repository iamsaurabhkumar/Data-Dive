"""
Single source of truth for "the creator's posts with their latest metrics".

Mock mode  → deterministic mock feed.
DB mode    → one query: content_posts joined to the latest metric_snapshot
             per post (DISTINCT ON), instead of one query per post.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentPost
from app.models.creator import CreatorProfile
from app.models.metric import MetricSnapshot
from app.services.analytics.records import PostRecord
from app.services.mock_data import get_mock_feed


async def ensure_creator_profile(db: AsyncSession, user_sub: str) -> str:
    """
    Return the creator_profiles.id for a Supabase user, creating the profile
    on first sight. The existing sync code uses id == user_id, which we keep.
    """
    uid = uuid.UUID(str(user_sub))
    row = (await db.execute(select(CreatorProfile).where(CreatorProfile.user_id == uid))).scalar_one_or_none()
    if row is None:
        row = (await db.execute(select(CreatorProfile).where(CreatorProfile.id == uid))).scalar_one_or_none()
    if row is None:
        row = CreatorProfile(id=uid, user_id=uid)
        db.add(row)
        await db.flush()
    return str(row.id)


async def load_posts(db: Optional[AsyncSession], creator_id: str) -> List[PostRecord]:
    if get_settings().mock_mode or db is None:
        return [PostRecord.from_feed_dict(p) for p in get_mock_feed()]

    latest = (
        select(MetricSnapshot)
        .distinct(MetricSnapshot.post_id)
        .order_by(MetricSnapshot.post_id, MetricSnapshot.captured_at.desc())
        .subquery()
    )
    stmt = (
        select(ContentPost, latest)
        .join(latest, latest.c.post_id == ContentPost.id)
        .where(ContentPost.creator_id == uuid.UUID(str(creator_id)))
    )
    rows = (await db.execute(stmt)).all()
    out: List[PostRecord] = []
    for row in rows:
        post: ContentPost = row[0]
        m = row._mapping
        out.append(PostRecord(
            id=str(post.id),
            platform=post.platform,
            content_type=post.content_type,
            title=post.title,
            published_at=post.published_at,
            views=int(m["views"] or 0),
            likes=int(m["likes"] or 0),
            comments=int(m["comments"] or 0),
            shares=int(m["shares"] or 0),
            saves=int(m["saves"] or 0),
            watch_time_hours=float(m["watch_time_hours"] or 0.0),
            thumbnail_url=post.thumbnail_url,
            external_post_id=post.external_post_id,
        ))
    return out


def sort_posts(posts: List[PostRecord], sort_by: str, sort_order: str) -> List[PostRecord]:
    reverse = sort_order != "asc"
    if sort_by in ("views", "likes", "comments", "shares", "saves"):
        return sorted(posts, key=lambda p: getattr(p, sort_by), reverse=reverse)
    # published_at: undated posts always last regardless of direction
    dated = [p for p in posts if p.published_at]
    undated = [p for p in posts if not p.published_at]
    dated.sort(key=lambda p: p.published_at, reverse=reverse)  # type: ignore[arg-type]
    return dated + undated
