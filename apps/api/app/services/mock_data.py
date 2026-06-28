"""
Mock data service for development.
Generates realistic fake content and metrics so the dashboard
can be developed without real API credentials.
"""
import uuid
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any


# Realistic YouTube video titles for a content creator
YOUTUBE_TITLES = [
    "Ultimate Desk Setup Tour 2026 — Minimal & Clean",
    "How I Edit Videos 10x Faster — Workflow Secrets",
    "Day in the Life of a Full-Time Creator",
    "5 Camera Tricks That Changed My Content",
    "Building My Dream Studio on a Budget",
    "Why I Switched from Premiere to DaVinci Resolve",
    "The Truth About YouTube Algorithm in 2026",
    "How I Script Videos That Get 1M+ Views",
    "Beginner Filmmaker Mistakes I Still Make",
    "Studio Vlog — Renovating My Workspace",
    "Top 10 Gadgets Every Creator Needs",
    "My Complete Lighting Setup Explained",
    "How to Grow on YouTube — Honest Advice",
    "Behind the Scenes of a Viral Video",
    "Reviewing Every Camera I've Used",
    "Morning Routine for Maximum Productivity",
    "How I Plan a Month of Content in 2 Hours",
    "Collab Day with @creator — BTS Vlog",
    "Q&A — Your Questions Answered",
    "The Equipment I Regret Buying",
    "Cinematic B-Roll Tutorial in 10 Minutes",
    "My Income Breakdown as a Creator",
    "Workspace Aesthetics That Boost Productivity",
    "Travel Vlog — Bali Content Trip",
    "One Year on YouTube — What I've Learned",
    "Short: 3 Quick Editing Hacks",
    "Short: POV — Setting Up a Shot",
    "Short: Unpacking the New Sony Camera",
    "Short: Before vs After Color Grade",
    "Short: My #1 Tip for New Creators",
]

# Realistic Instagram post captions
INSTAGRAM_CAPTIONS = [
    "New studio vibes ✨ What do you think of the setup?",
    "Behind the scenes of today's shoot 🎬",
    "Golden hour hits different in the studio 🌅",
    "POV: You just wrapped a 12-hour edit session",
    "The workspace glow-up nobody asked for 🔥",
    "Magic hour content creation 📸",
    "Sound on 🔊 New transitions pack dropping soon",
    "Clean desk, clear mind 🧠",
    "Reel: 5 transitions you need to know",
    "Reel: Day in my life as a creator",
    "Reel: Studio tour in 30 seconds",
    "Reel: Camera settings I use for everything",
    "Reel: Before & after edit comparison",
    "Reel: Pack my camera bag with me",
    "Reel: POV filming a product shoot",
    "Carousel: My top 5 editing tools ranked",
    "Carousel: Gear that actually matters",
    "Minimalist workspace inspo 🤍",
    "Content batch day — 6 videos done ✅",
    "Reel: Quick tip — nail your white balance",
    "The corner of my studio I never show 😂",
    "Reel: How I film myself alone",
    "New camera who dis 📷",
    "Aesthetic setup goals ✨",
    "Reel: 3 lighting hacks under $50",
    "Sunset shoots > everything else",
    "Reel: My morning routine as a creator",
    "This angle though 🎯",
    "Reel: Packing for a content trip",
    "Late night editing session 🌙",
]

THUMBNAILS_YT = [
    "https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "https://img.youtube.com/vi/jNQXAC9IVRw/maxresdefault.jpg",
    "https://img.youtube.com/vi/9bZkp7q19f0/maxresdefault.jpg",
]


def _generate_mock_youtube_posts(count: int = 30) -> List[Dict[str, Any]]:
    """Generate realistic mock YouTube posts."""
    posts = []
    now = datetime.now(timezone.utc)

    for i in range(min(count, len(YOUTUBE_TITLES))):
        title = YOUTUBE_TITLES[i]
        is_short = title.startswith("Short:")
        published = now - timedelta(days=random.randint(1, 180), hours=random.randint(0, 23))

        # Shorts get more views but less watch time
        if is_short:
            views = random.randint(50_000, 2_000_000)
            likes = int(views * random.uniform(0.03, 0.08))
            comments = int(views * random.uniform(0.001, 0.005))
            watch_time = round(views * random.uniform(0.0001, 0.0003), 2)  # ~15-30 seconds avg
        else:
            views = random.randint(5_000, 500_000)
            likes = int(views * random.uniform(0.02, 0.06))
            comments = int(views * random.uniform(0.002, 0.01))
            watch_time = round(views * random.uniform(0.001, 0.005), 2)  # ~5-15 min avg

        posts.append({
            "platform": "YouTube",
            "external_post_id": f"yt_{uuid.uuid4().hex[:11]}",
            "title": title.replace("Short: ", "") if is_short else title,
            "content_type": "Short" if is_short else "Long-form",
            "thumbnail_url": random.choice(THUMBNAILS_YT),
            "published_at": published.isoformat(),
            "metrics": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "watch_time_hours": watch_time,
                "shares": int(likes * random.uniform(0.05, 0.15)),
                "saves": 0,
            },
        })

    return posts


def _generate_mock_instagram_posts(count: int = 30) -> List[Dict[str, Any]]:
    """Generate realistic mock Instagram posts."""
    posts = []
    now = datetime.now(timezone.utc)

    for i in range(min(count, len(INSTAGRAM_CAPTIONS))):
        caption = INSTAGRAM_CAPTIONS[i]
        is_reel = "Reel:" in caption or "reel" in caption.lower()
        is_carousel = "Carousel:" in caption

        if is_reel:
            content_type = "Reel"
            views = random.randint(10_000, 1_500_000)
        elif is_carousel:
            content_type = "Post"
            views = random.randint(3_000, 80_000)
        else:
            content_type = "Post"
            views = random.randint(2_000, 100_000)

        likes = int(views * random.uniform(0.04, 0.12))
        comments = int(views * random.uniform(0.002, 0.015))
        published = now - timedelta(days=random.randint(1, 150), hours=random.randint(0, 23))

        clean_title = caption.replace("Reel: ", "").replace("Carousel: ", "")

        posts.append({
            "platform": "Instagram",
            "external_post_id": f"ig_{uuid.uuid4().hex[:17]}",
            "title": clean_title,
            "content_type": content_type,
            "thumbnail_url": f"https://picsum.photos/seed/{uuid.uuid4().hex[:8]}/400/400",
            "published_at": published.isoformat(),
            "metrics": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "watch_time_hours": round(views * 0.00005, 2) if is_reel else 0.0,
                "shares": int(likes * random.uniform(0.02, 0.1)),
                "saves": int(likes * random.uniform(0.1, 0.3)),
            },
        })

    return posts


def get_mock_feed(platform: str | None = None, content_type: str | None = None) -> List[Dict[str, Any]]:
    """
    Get the unified mock content feed.
    Optionally filter by platform and/or content_type.
    """
    youtube_posts = _generate_mock_youtube_posts()
    instagram_posts = _generate_mock_instagram_posts()
    all_posts = youtube_posts + instagram_posts

    # Apply filters
    if platform:
        all_posts = [p for p in all_posts if p["platform"].lower() == platform.lower()]
    if content_type:
        all_posts = [p for p in all_posts if p["content_type"].lower() == content_type.lower()]

    # Sort by published_at descending (newest first)
    all_posts.sort(key=lambda p: p["published_at"], reverse=True)

    return all_posts


def get_mock_summary() -> Dict[str, Any]:
    """Get aggregated KPI summary from mock data."""
    feed = get_mock_feed()

    total_views = sum(p["metrics"]["views"] for p in feed)
    total_likes = sum(p["metrics"]["likes"] for p in feed)
    total_comments = sum(p["metrics"]["comments"] for p in feed)
    total_posts = len(feed)

    yt_views = sum(p["metrics"]["views"] for p in feed if p["platform"] == "YouTube")
    ig_views = sum(p["metrics"]["views"] for p in feed if p["platform"] == "Instagram")

    # Find best performing content type
    type_views = {}
    for p in feed:
        ct = p["content_type"]
        type_views[ct] = type_views.get(ct, 0) + p["metrics"]["views"]
    top_type = max(type_views, key=type_views.get) if type_views else "N/A"

    return {
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_posts": total_posts,
        "avg_views_per_post": round(total_views / total_posts) if total_posts else 0,
        "avg_engagement_rate": round((total_likes + total_comments) / total_views * 100, 2) if total_views else 0,
        "top_platform": "YouTube" if yt_views > ig_views else "Instagram",
        "top_content_type": top_type,
        "platform_breakdown": {
            "youtube": {
                "posts": len([p for p in feed if p["platform"] == "YouTube"]),
                "views": yt_views,
            },
            "instagram": {
                "posts": len([p for p in feed if p["platform"] == "Instagram"]),
                "views": ig_views,
            },
        },
    }


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
