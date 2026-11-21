import re
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
SHORT_MAX_SECONDS = 180  # YouTube Shorts may be up to 3 minutes (since Oct 2024)


def parse_iso8601_duration(duration: str) -> int | None:
    """'PT1M23S' -> 83 seconds. Returns None for unparseable input."""
    if not duration:
        return None
    m = _DURATION_RE.match(duration)
    if not m:
        return None
    days, hours, minutes, seconds = (int(x) if x else 0 for x in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def classify_youtube_video(duration: str, title: str = "", description: str = "") -> str:
    seconds = parse_iso8601_duration(duration)
    if seconds is None:
        return "Long-form"
    if seconds <= 60:
        return "Short"
    if seconds <= SHORT_MAX_SECONDS and "#shorts" in f"{title} {description}".lower():
        return "Short"
    return "Long-form"

class YouTubeService:
    """Client for interacting with the YouTube Data API v3."""

    def __init__(self, provider_token: str):
        # We initialize the client using the OAuth token obtained via Supabase
        credentials = Credentials(token=provider_token)
        self.youtube = build("youtube", "v3", credentials=credentials)

    def fetch_recent_videos(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """
        Fetches the latest videos for the authenticated user.
        Requires 'youtube.readonly' scope.
        """
        try:
            # 1. Get the authenticated user's channel ID and uploads playlist ID
            channel_response = self.youtube.channels().list(
                part="contentDetails",
                mine=True
            ).execute()

            if not channel_response.get("items"):
                return []

            channel = channel_response["items"][0]
            uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

            # 2. Fetch the latest videos from the uploads playlist
            playlist_response = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=max_results
            ).execute()

            video_items = playlist_response.get("items", [])
            if not video_items:
                return []

            # 3. Get detailed stats for these videos
            video_ids = [item["contentDetails"]["videoId"] for item in video_items]
            
            # The API allows a max of 50 IDs per request, we are fetching max_results (e.g. 30)
            stats_response = self.youtube.videos().list(
                part="statistics,snippet,contentDetails",
                id=",".join(video_ids)
            ).execute()

            stats_items = stats_response.get("items", [])
            return self._normalize_videos(stats_items)

        except Exception as e:
            print(f"Error fetching YouTube data: {e}")
            raise

    def _normalize_videos(self, raw_videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalizes YouTube API response into our internal format."""
        normalized = []
        for video in raw_videos:
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            content_details = video.get("contentDetails", {})
            
            # The Data API does not flag Shorts explicitly: <= 60s is a Short, and
            # 60–180s counts when the creator tagged it #shorts.
            content_type = classify_youtube_video(
                content_details.get("duration", ""), snippet.get("title", ""), snippet.get("description", "")
            )

            normalized.append({
                "platform": "YouTube",
                "external_post_id": video["id"],
                "title": snippet.get("title", ""),
                "content_type": content_type,
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "published_at": snippet.get("publishedAt"),
                "metrics": {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "watch_time_hours": 0.0,  # Not available in basic Data API v3 without Analytics API
                    "shares": 0,
                    "saves": 0,
                }
            })
            
        return normalized
