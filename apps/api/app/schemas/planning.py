"""Pydantic schemas for analytics, ideas and the Kanban board."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.repositories.domain import PIPELINE, STAGES


# ---- analytics ---------------------------------------------------------
class GroupStatSchema(BaseModel):
    key: str
    label: str
    posts: int
    avg_views: int
    median_views: int
    avg_engagement_rate: float
    lift: float
    raw_lift: float
    confidence: str
    platforms: List[str] = []
    example_titles: List[str] = []


class FindingSchema(BaseModel):
    kind: str
    headline: str
    detail: str
    confidence: str
    evidence: Dict[str, Any] = {}


class SlotSchema(BaseModel):
    weekday: int
    weekday_label: str
    hour_bucket: str
    hour_range: str
    lift: float
    posts: int
    confidence: str


class PatternsResponse(BaseModel):
    timezone: str
    sample_size: int
    topics: List[GroupStatSchema]
    formats: List[GroupStatSchema]
    weekdays: List[GroupStatSchema]
    hour_buckets: List[GroupStatSchema]
    slots: List[GroupStatSchema]
    best_slots: Dict[str, List[SlotSchema]]
    findings: List[FindingSchema]


class PlatformSummarySchema(BaseModel):
    platform: str
    posts: int
    total_views: int
    total_engagement: int
    avg_views: int
    median_views: int
    avg_engagement_rate: float
    watch_time_hours: float
    best_format: Optional[str]
    best_format_lift: float
    posts_last_30d: int
    posts_per_week: float
    momentum: float
    top_posts: List[Dict[str, Any]] = []


class OverviewResponse(BaseModel):
    total_posts: int
    total_views: int
    total_likes: int
    total_comments: int
    total_engagement: int
    avg_views_per_post: int
    avg_engagement_rate: float
    top_platform: str
    top_content_type: str
    platforms: List[PlatformSummarySchema]
    content_type_counts: Dict[str, int]


class AccuracySchema(BaseModel):
    count: int
    mape: Optional[float] = None
    hit_rate: Optional[float] = None
    bias: Optional[float] = None
    trend: Optional[float] = None


class CalibrationSchema(BaseModel):
    creator_id: str
    platform: str
    content_type: str
    factor: float
    samples: int
    updated_at: str


class LearningResponse(BaseModel):
    accuracy: AccuracySchema
    by_platform: Dict[str, AccuracySchema]
    calibrations: List[CalibrationSchema]
    reviews: List[Dict[str, Any]]


# ---- ideas ---------------------------------------------------------------
class PredictionSchema(BaseModel):
    platform: str
    content_type: str
    expected_views: int
    views_low: int
    views_high: int
    expected_engagement_rate: float
    expected_engagement: int
    confidence: float
    confidence_label: str
    factors: Dict[str, Any] = {}
    recommended_slot: Optional[Dict[str, Any]] = None
    model_version: str = "v1"


class IdeaSchema(BaseModel):
    id: str
    title: str
    hook: str
    outline: List[str]
    platform: str
    content_type: str
    topics: List[str]
    strategy: str
    rationale: str
    recommended_slot: Optional[Dict[str, Any]] = None
    prediction: Dict[str, Any] = {}
    confidence_score: float
    description: str = ""
    source: str = "analytics"
    status: str = "pending"
    created_at: str
    trend_id: Optional[str] = None
    kit: Dict[str, Any] = {}
    enrichment_status: Optional[str] = None


class ScoredTrendSchema(BaseModel):
    trend: Dict[str, Any]
    score: float
    relevance: float
    momentum: float
    freshness: float
    matched_topics: List[str]
    topic_fit: float
    age_hours: float


class NextProjectRequest(BaseModel):
    exclude_trend_ids: List[str] = Field(default_factory=list, max_length=50)
    platform: Optional[str] = Field(None, pattern="^(YouTube|Instagram)$")
    enrich: bool = True


class NextProjectResponse(BaseModel):
    idea: "IdeaSchema"
    trend: Optional[ScoredTrendSchema] = None
    alternatives: List[ScoredTrendSchema] = []
    trends_considered: int = 0
    fallback_reason: Optional[str] = None       # no_trends | no_relevant_trends
    enrichment: str = "disabled"                # queued | unavailable | disabled
    trend_refresh: Optional[str] = None         # queued when there were no trends at all


class GenerateIdeasRequest(BaseModel):
    count: int = Field(6, ge=1, le=12)
    seed: Optional[int] = None
    enrich: bool = Field(False, description="Queue an LLM pass (worker) to polish title/hook/outline. Ignored in mock mode.")


class IdeasListResponse(BaseModel):
    ideas: List[IdeaSchema]
    total: int


# ---- kanban --------------------------------------------------------------
class CardSchema(BaseModel):
    id: str
    creator_id: str
    title: str
    hook: str = ""
    outline: List[str] = []
    platform: str
    content_type: str
    topics: List[str] = []
    stage: str
    position: int = 0
    suggestion_id: Optional[str] = None
    post_id: Optional[str] = None
    scheduled_for: Optional[str] = None
    published_at: Optional[str] = None
    prediction: Optional[Dict[str, Any]] = None
    recommended_slot: Optional[Dict[str, Any]] = None
    strategy: Optional[str] = None
    rationale: Optional[str] = None
    notes: str = ""
    created_at: str
    updated_at: str
    review: Optional[Dict[str, Any]] = None
    linked_post: Optional[Dict[str, Any]] = None
    events: Optional[List[Dict[str, Any]]] = None


class ColumnSchema(BaseModel):
    stage: str
    cards: List[CardSchema]


class BoardResponse(BaseModel):
    columns: List[ColumnSchema]
    total: int
    stages: List[str] = list(PIPELINE)   # columns, in order
    all_stages: List[str] = list(STAGES) # includes the terminal "reviewed" sub-state


class CardCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    platform: str = "YouTube"
    content_type: Optional[str] = None
    hook: Optional[str] = ""
    outline: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    notes: Optional[str] = ""
    stage: Optional[str] = "idea"
    scheduled_for: Optional[str] = None


class CardUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    hook: Optional[str] = None
    outline: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    notes: Optional[str] = None
    scheduled_for: Optional[str] = None
    published_at: Optional[str] = None
    platform: Optional[str] = None
    content_type: Optional[str] = None


class CardMoveRequest(BaseModel):
    stage: str
    position: Optional[int] = Field(None, ge=0)
    note: str = ""


class LinkPostRequest(BaseModel):
    post_id: Optional[str] = None
    auto: bool = False


class ReviewRequest(BaseModel):
    min_age_days: float = Field(0.0, ge=0)
