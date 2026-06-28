"""Pydantic schemas for API request/response serialization."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class MetricsSchema(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    watch_time_hours: float = 0.0
    shares: int = 0
    saves: int = 0


class ContentPostSchema(BaseModel):
    id: Optional[str] = None
    platform: str
    external_post_id: str
    title: str
    content_type: str
    thumbnail_url: Optional[str] = None
    published_at: Optional[str] = None
    metrics: MetricsSchema

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    posts: List[ContentPostSchema]
    total: int
    page: int = 1
    per_page: int = 60


class SummaryResponse(BaseModel):
    total_views: int
    total_likes: int
    total_comments: int
    total_posts: int
    avg_views_per_post: int
    avg_engagement_rate: float
    top_platform: str
    top_content_type: str
    platform_breakdown: dict


class CreatorProfileSchema(BaseModel):
    id: str
    user_id: str
    email: Optional[str] = None
    youtube_connected: bool = False
    youtube_channel_id: Optional[str] = None
    instagram_connected: bool = False
    instagram_user_id: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    posts_synced: int
    message: str


class WhatWorksSchema(BaseModel):
    top_content_type: str
    top_platform: str
    recommendation_text: str

class PerformanceDataSchema(BaseModel):
    date: str
    youtube_views: int
    instagram_views: int

class InsightsResponse(BaseModel):
    what_works: WhatWorksSchema
    performance_data: List[PerformanceDataSchema]
