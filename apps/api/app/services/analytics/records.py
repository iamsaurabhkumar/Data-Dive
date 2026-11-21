"""
Normalized post record used by the analytics engine.

Both the mock feed and the database (ContentPost + latest MetricSnapshot)
are converted into PostRecord so every downstream computation is
source-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

PLATFORMS = ("YouTube", "Instagram")
CONTENT_TYPES = ("Short", "Long-form", "Reel", "Post")

# Which formats exist on which platform
PLATFORM_FORMATS: Dict[str, tuple] = {
    "YouTube": ("Short", "Long-form"),
    "Instagram": ("Reel", "Post"),
}

HOUR_BUCKETS = ("morning", "midday", "evening", "night")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def hour_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "midday"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def bucket_hour_range(bucket: str) -> str:
    return {
        "morning": "06:00–12:00",
        "midday": "12:00–17:00",
        "evening": "17:00–22:00",
        "night": "22:00–06:00",
    }[bucket]


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO strings / datetimes into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class PostRecord:
    id: str
    platform: str
    content_type: str
    title: str
    published_at: Optional[datetime]
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    watch_time_hours: float = 0.0
    thumbnail_url: Optional[str] = None
    external_post_id: Optional[str] = None
    topics: List[str] = field(default_factory=list)  # filled by the topic extractor

    # ---- derived -------------------------------------------------------
    @property
    def engagement(self) -> int:
        return self.likes + self.comments + self.shares + self.saves

    @property
    def engagement_rate(self) -> float:
        """Engagement per view. Single definition shared by every feature."""
        return self.engagement / self.views if self.views > 0 else 0.0

    def local_published(self, tz: str = "UTC") -> Optional[datetime]:
        if self.published_at is None:
            return None
        try:
            return self.published_at.astimezone(ZoneInfo(tz))
        except Exception:
            return self.published_at

    def weekday(self, tz: str = "UTC") -> Optional[int]:
        dt = self.local_published(tz)
        return dt.weekday() if dt else None

    def hour_bucket(self, tz: str = "UTC") -> Optional[str]:
        dt = self.local_published(tz)
        return hour_bucket(dt.hour) if dt else None

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.published_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        return max((now - self.published_at).total_seconds() / 86400.0, 0.0)

    # ---- constructors --------------------------------------------------
    @classmethod
    def from_feed_dict(cls, p: Dict[str, Any]) -> "PostRecord":
        m = p.get("metrics", {}) or {}
        return cls(
            id=str(p.get("id") or p.get("external_post_id")),
            platform=p["platform"],
            content_type=p["content_type"],
            title=p.get("title") or "",
            published_at=parse_dt(p.get("published_at")),
            views=int(m.get("views", 0) or 0),
            likes=int(m.get("likes", 0) or 0),
            comments=int(m.get("comments", 0) or 0),
            shares=int(m.get("shares", 0) or 0),
            saves=int(m.get("saves", 0) or 0),
            watch_time_hours=float(m.get("watch_time_hours", 0.0) or 0.0),
            thumbnail_url=p.get("thumbnail_url"),
            external_post_id=p.get("external_post_id"),
        )

    def to_feed_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "external_post_id": self.external_post_id or self.id,
            "title": self.title,
            "content_type": self.content_type,
            "thumbnail_url": self.thumbnail_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "metrics": {
                "views": self.views,
                "likes": self.likes,
                "comments": self.comments,
                "watch_time_hours": self.watch_time_hours,
                "shares": self.shares,
                "saves": self.saves,
            },
        }
