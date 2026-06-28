import httpx
from typing import List, Dict, Any
from datetime import datetime

class InstagramService:
    """Client for interacting with the Meta Graph API for Instagram."""
    
    BASE_URL = "https://graph.facebook.com/v20.0"

    def __init__(self, provider_token: str):
        self.provider_token = provider_token
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            params={"access_token": self.provider_token}
        )

    async def close(self):
        await self.client.aclose()

    async def fetch_recent_posts(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """
        Fetches the latest posts for the authenticated user's linked Instagram Professional account.
        Requires 'instagram_basic' and 'instagram_manage_insights' scopes via Facebook Login.
        """
        try:
            # 1. Get the Facebook Pages the user manages
            pages_resp = await self.client.get("/me/accounts")
            pages_resp.raise_for_status()
            pages = pages_resp.json().get("data", [])
            
            if not pages:
                return []
                
            # 2. Find the Instagram Business Account linked to one of the pages
            ig_user_id = None
            for page in pages:
                page_id = page["id"]
                ig_resp = await self.client.get(
                    f"/{page_id}", 
                    params={"fields": "instagram_business_account"}
                )
                if ig_resp.is_success:
                    ig_data = ig_resp.json()
                    if "instagram_business_account" in ig_data:
                        ig_user_id = ig_data["instagram_business_account"]["id"]
                        break
                        
            if not ig_user_id:
                return []

            # 3. Fetch the latest media for this IG account
            media_resp = await self.client.get(
                f"/{ig_user_id}/media",
                params={
                    "fields": "id,caption,media_type,media_product_type,media_url,thumbnail_url,timestamp",
                    "limit": max_results
                }
            )
            media_resp.raise_for_status()
            media_items = media_resp.json().get("data", [])

            if not media_items:
                return []

            # 4. Fetch insights for each media item
            normalized_posts = []
            for item in media_items:
                media_id = item["id"]
                media_type = item.get("media_type")
                
                # Different media types require different insight metrics
                metrics_to_fetch = "impressions,reach,saved,shares" 
                if media_type == "VIDEO":
                    metrics_to_fetch = "impressions,reach,saved,shares,video_views"
                    
                insights_resp = await self.client.get(
                    f"/{media_id}/insights",
                    params={"metric": metrics_to_fetch}
                )
                
                insights_data = {}
                if insights_resp.is_success:
                    for insight in insights_resp.json().get("data", []):
                        insights_data[insight["name"]] = insight["values"][0]["value"]
                
                # Fetch comments and likes count (they are on the media object directly, but let's query them)
                # To save API calls, we could have fetched them in step 3. Let's do a quick separate call, 
                # or we can fetch them here.
                engagement_resp = await self.client.get(
                    f"/{media_id}",
                    params={"fields": "like_count,comments_count"}
                )
                if engagement_resp.is_success:
                    eng_data = engagement_resp.json()
                    insights_data["like_count"] = eng_data.get("like_count", 0)
                    insights_data["comments_count"] = eng_data.get("comments_count", 0)
                else:
                    insights_data["like_count"] = 0
                    insights_data["comments_count"] = 0

                normalized_posts.append(self._normalize_post(item, insights_data))
                
            return normalized_posts

        except Exception as e:
            print(f"Error fetching Instagram data: {e}")
            raise
        finally:
            await self.close()

    def _normalize_post(self, media: Dict[str, Any], insights: Dict[str, int]) -> Dict[str, Any]:
        """Normalizes Meta Graph API response into our internal format."""
        # Classify content type
        media_type = media.get("media_type")
        product_type = media.get("media_product_type")
        
        content_type = "Post"
        if media_type == "VIDEO":
            if product_type == "REELS":
                content_type = "Reel"
            else:
                content_type = "Long-form"

        return {
            "platform": "Instagram",
            "external_post_id": media["id"],
            "title": media.get("caption", "")[:100],  # Use first 100 chars of caption as title
            "content_type": content_type,
            "thumbnail_url": media.get("thumbnail_url") or media.get("media_url"),
            "published_at": media.get("timestamp"),
            "metrics": {
                # Reels use video_views or plays, regular posts use impressions/reach as a fallback for 'views'
                "views": insights.get("video_views", insights.get("impressions", 0)),
                "likes": insights.get("like_count", 0),
                "comments": insights.get("comments_count", 0),
                "watch_time_hours": 0.0,
                "shares": insights.get("shares", 0),
                "saves": insights.get("saved", 0),
            }
        }
