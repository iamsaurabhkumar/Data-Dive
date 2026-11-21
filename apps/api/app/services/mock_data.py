"""
Mock data service for development.

Generates realistic fake content and metrics so the dashboard can be developed
without real API credentials.

IMPORTANT: the dataset is *deterministic* (seeded RNG, stable ids, stable
publish dates relative to a fixed anchor) and cached per process. Feed,
summary, analytics, predictions and reviews all see the same posts.
"""
import random
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List

from app.config import get_settings

# Fixed anchor so weekday/hour patterns are stable between runs.
MOCK_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

# (title, topic bucket) — topics are used to seed realistic "what works" patterns
YOUTUBE_TITLES = [
    ("Ultimate Desk Setup Tour 2026 — Minimal & Clean", "desk setup"),
    ("How I Edit Videos 10x Faster — Workflow Secrets", "editing"),
    ("Day in the Life of a Full-Time Creator", "day in the life"),
    ("5 Camera Tricks That Changed My Content", "camera"),
    ("Building My Dream Studio on a Budget", "studio"),
    ("Why I Switched from Premiere to DaVinci Resolve", "editing"),
    ("The Truth About YouTube Algorithm in 2026", "youtube growth"),
    ("How I Script Videos That Get 1M+ Views", "youtube growth"),
    ("Beginner Filmmaker Mistakes I Still Make", "camera"),
    ("Studio Vlog — Renovating My Workspace", "studio"),
    ("Top 10 Gadgets Every Creator Needs", "gear"),
    ("My Complete Lighting Setup Explained", "lighting"),
    ("How to Grow on YouTube — Honest Advice", "youtube growth"),
    ("Behind the Scenes of a Viral Video", "behind the scenes"),
    ("Reviewing Every Camera I've Used", "camera"),
    ("Morning Routine for Maximum Productivity", "productivity"),
    ("How I Plan a Month of Content in 2 Hours", "productivity"),
    ("Collab Day with @creator — BTS Vlog", "behind the scenes"),
    ("Q&A — Your Questions Answered", "q&a"),
    ("The Equipment I Regret Buying", "gear"),
    ("Cinematic B-Roll Tutorial in 10 Minutes", "editing"),
    ("My Income Breakdown as a Creator", "creator income"),
    ("Workspace Aesthetics That Boost Productivity", "desk setup"),
    ("Travel Vlog — Bali Content Trip", "travel"),
    ("One Year on YouTube — What I've Learned", "youtube growth"),
    ("Short: 3 Quick Editing Hacks", "editing"),
    ("Short: POV — Setting Up a Shot", "camera"),
    ("Short: Unpacking the New Sony Camera", "camera"),
    ("Short: Before vs After Color Grade", "editing"),
    ("Short: My #1 Tip for New Creators", "youtube growth"),
]

INSTAGRAM_CAPTIONS = [
    ("New studio vibes ✨ What do you think of the setup?", "studio"),
    ("Behind the scenes of today's shoot 🎬", "behind the scenes"),
    ("Golden hour hits different in the studio 🌅", "lighting"),
    ("POV: You just wrapped a 12-hour edit session", "editing"),
    ("The workspace glow-up nobody asked for 🔥", "desk setup"),
    ("Magic hour content creation 📸", "lighting"),
    ("Sound on 🔊 New transitions pack dropping soon", "editing"),
    ("Clean desk, clear mind 🧠", "desk setup"),
    ("Reel: 5 transitions you need to know", "editing"),
    ("Reel: Day in my life as a creator", "day in the life"),
    ("Reel: Studio tour in 30 seconds", "studio"),
    ("Reel: Camera settings I use for everything", "camera"),
    ("Reel: Before & after edit comparison", "editing"),
    ("Reel: Pack my camera bag with me", "gear"),
    ("Reel: POV filming a product shoot", "camera"),
    ("Carousel: My top 5 editing tools ranked", "editing"),
    ("Carousel: Gear that actually matters", "gear"),
    ("Minimalist workspace inspo 🤍", "desk setup"),
    ("Content batch day — 6 videos done ✅", "productivity"),
    ("Reel: Quick tip — nail your white balance", "camera"),
    ("The corner of my studio I never show 😂", "studio"),
    ("Reel: How I film myself alone", "camera"),
    ("New camera who dis 📷", "camera"),
    ("Aesthetic setup goals ✨", "desk setup"),
    ("Reel: 3 lighting hacks under $50", "lighting"),
    ("Sunset shoots > everything else", "lighting"),
    ("Reel: My morning routine as a creator", "productivity"),
    ("This angle though 🎯", "camera"),
    ("Reel: Packing for a content trip", "travel"),
    ("Late night editing session 🌙", "editing"),
]

THUMBNAILS_YT = [
    "https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "https://img.youtube.com/vi/jNQXAC9IVRw/maxresdefault.jpg",
    "https://img.youtube.com/vi/9bZkp7q19f0/maxresdefault.jpg",
]

# Hidden "ground truth" multipliers so the analytics engine has real patterns to find.
_TOPIC_LIFT = {
    "editing": 1.6,
    "camera": 1.25,
    "youtube growth": 1.4,
    "desk setup": 1.1,
    "studio": 0.9,
    "lighting": 1.05,
    "gear": 0.85,
    "productivity": 1.0,
    "behind the scenes": 0.8,
    "travel": 0.7,
    "creator income": 1.3,
    "q&a": 0.6,
    "day in the life": 0.95,
}
# Tue/Thu/Sat evenings perform best in the fixture
_WEEKDAY_LIFT = {0: 0.9, 1: 1.25, 2: 0.95, 3: 1.2, 4: 1.0, 5: 1.3, 6: 0.85}
_HOUR_LIFT = {"morning": 0.9, "midday": 1.0, "evening": 1.3, "night": 0.8}


def _hour_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "midday"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _stable_id(prefix: str, index: int) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, f'datadive/{prefix}/{index}').hex[:12]}"


def _generate_mock_youtube_posts(rng: random.Random) -> List[Dict[str, Any]]:
    posts = []
    for i, (title, topic) in enumerate(YOUTUBE_TITLES):
        is_short = title.startswith("Short:")
        published = MOCK_NOW - timedelta(days=rng.randint(1, 180), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        lift = _TOPIC_LIFT[topic] * _WEEKDAY_LIFT[published.weekday()] * _HOUR_LIFT[_hour_bucket(published.hour)]

        if is_short:
            views = int(rng.randint(50_000, 600_000) * lift)
            likes = int(views * rng.uniform(0.03, 0.08))
            comments = int(views * rng.uniform(0.001, 0.005))
            watch_time = round(views * rng.uniform(0.0001, 0.0003), 2)
        else:
            views = int(rng.randint(8_000, 120_000) * lift)
            likes = int(views * rng.uniform(0.02, 0.06))
            comments = int(views * rng.uniform(0.002, 0.01))
            watch_time = round(views * rng.uniform(0.001, 0.005), 2)

        pid = _stable_id("yt", i)
        posts.append({
            "id": pid,
            "platform": "YouTube",
            "external_post_id": pid,
            "title": title.replace("Short: ", "") if is_short else title,
            "content_type": "Short" if is_short else "Long-form",
            "thumbnail_url": THUMBNAILS_YT[i % len(THUMBNAILS_YT)],
            "published_at": published.isoformat(),
            "metrics": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "watch_time_hours": watch_time,
                "shares": int(likes * rng.uniform(0.05, 0.15)),
                "saves": 0,
            },
        })
    return posts


def _generate_mock_instagram_posts(rng: random.Random) -> List[Dict[str, Any]]:
    posts = []
    for i, (caption, topic) in enumerate(INSTAGRAM_CAPTIONS):
        is_reel = caption.startswith("Reel:")
        is_carousel = caption.startswith("Carousel:")
        published = MOCK_NOW - timedelta(days=rng.randint(1, 150), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        lift = _TOPIC_LIFT[topic] * _WEEKDAY_LIFT[published.weekday()] * _HOUR_LIFT[_hour_bucket(published.hour)]

        if is_reel:
            content_type = "Reel"
            views = int(rng.randint(15_000, 400_000) * lift)
        elif is_carousel:
            content_type = "Post"
            views = int(rng.randint(4_000, 40_000) * lift)
        else:
            content_type = "Post"
            views = int(rng.randint(2_500, 30_000) * lift)

        likes = int(views * rng.uniform(0.04, 0.12))
        comments = int(views * rng.uniform(0.002, 0.015))
        clean_title = caption.replace("Reel: ", "").replace("Carousel: ", "")
        pid = _stable_id("ig", i)

        posts.append({
            "id": pid,
            "platform": "Instagram",
            "external_post_id": pid,
            "title": clean_title,
            "content_type": content_type,
            "thumbnail_url": f"https://picsum.photos/seed/{pid}/400/400",
            "published_at": published.isoformat(),
            "metrics": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "watch_time_hours": round(views * 0.00005, 2) if is_reel else 0.0,
                "shares": int(likes * rng.uniform(0.02, 0.1)),
                "saves": int(likes * rng.uniform(0.1, 0.3)),
            },
        })
    return posts


@lru_cache(maxsize=1)
def _dataset() -> List[Dict[str, Any]]:
    rng = random.Random(get_settings().mock_seed)
    posts = _generate_mock_youtube_posts(rng) + _generate_mock_instagram_posts(rng)
    posts.sort(key=lambda p: p["published_at"], reverse=True)
    return posts


def get_mock_feed(platform: str | None = None, content_type: str | None = None) -> List[Dict[str, Any]]:
    """Unified mock content feed (copies, so callers can mutate safely)."""
    posts = [dict(p, metrics=dict(p["metrics"])) for p in _dataset()]
    if platform and platform.lower() != "all":
        posts = [p for p in posts if p["platform"].lower() == platform.lower()]
    if content_type and content_type.lower() != "all":
        posts = [p for p in posts if p["content_type"].lower() == content_type.lower()]
    return posts


def get_mock_post(post_id: str) -> Dict[str, Any] | None:
    for p in _dataset():
        if p["id"] == post_id or p["external_post_id"] == post_id:
            return dict(p, metrics=dict(p["metrics"]))
    return None


def get_mock_creator_profile() -> Dict[str, Any]:
    """Return a mock creator profile."""
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "creator@datadive.dev",
        "youtube_connected": True,
        "youtube_channel_id": "UC_mock_channel_id",
        "instagram_connected": True,
        "instagram_user_id": "ig_mock_user_id",
    }
