from typing import List, Dict, Any
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

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
            
            # Determine if Short or Long-form based on duration
            # Duration format is ISO 8601 (e.g., PT1M23S)
            # A rough heuristic: if duration contains 'M' and number before M is > 1, or 'H', it's long-form.
            # For simplicity, we just check if "S" is the only thing and it's less than 60s, but 
            # YouTube API doesn't strictly categorize shorts. We'll label anything under 60s as "Short".
            duration = content_details.get("duration", "")
            content_type = "Long-form"
            if "M" not in duration and "H" not in duration and "S" in duration:
                content_type = "Short"
            elif "PT1M" in duration and duration.endswith("S") and int(duration.split("M")[0].replace("PT", "")) == 0:
                 # It's less than 60 seconds (but strictly not standard PT format)
                 content_type = "Short"

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
