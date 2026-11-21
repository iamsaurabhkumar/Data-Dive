"""
ContentSuggestion model — AI-generated content recommendations for creators.

Populated by the ARQ worker after vector similarity matching + LLM reasoning.
The 'status' column drives Supabase Realtime WebSocket subscriptions:
when the worker inserts status="pending", the frontend receives the card instantly.

FK constraints:
  - creator_id → ON DELETE CASCADE (GDPR: wipe all suggestions when creator deletes profile)
  - trend_id   → ON DELETE SET NULL (TTL cleanup of stale trends must NOT delete suggestion cards)
"""
import uuid

from sqlalchemy import (
    Column, String, Text, Float, DateTime, ForeignKey,
    func, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


# Valid status transitions:
# pending → accepted → converted_to_kanban
# pending → rejected
SUGGESTION_STATUSES = ("pending", "accepted", "rejected", "converted_to_kanban")


class ContentSuggestion(Base):
    """
    AI-generated content recommendation linked to a creator.

    Each suggestion optionally references the PlatformTrend that
    inspired it, along with the LLM's reasoning chain and a
    confidence score from vector similarity.
    """
    __tablename__ = "content_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK: Creator who owns this suggestion
    # ON DELETE CASCADE — GDPR compliance: delete profile → wipe all suggestions
    creator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("creator_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # FK: The trend that inspired this suggestion (nullable)
    # ON DELETE SET NULL — TTL cleanup of expired trends must NOT cascade-delete suggestions
    trend_id = Column(
        UUID(as_uuid=True),
        ForeignKey("platform_trends.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # AI-generated content
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)            # LLM reasoning chain for transparency

    # Relevance score from vector cosine similarity (0.0 to 1.0)
    confidence_score = Column(Float, nullable=True, default=0.0)

    # Workflow status — drives Supabase Realtime subscriptions
    status = Column(String(30), nullable=False, default="pending", index=True)

    # ---- Phase 3: analytics-driven idea fields (all nullable for backwards compatibility) ----
    source = Column(String(30), nullable=False, server_default="trend")   # trend | analytics | manual
    hook = Column(Text, nullable=True)
    outline = Column(JSONB, nullable=True)               # list[str]
    platform = Column(String(20), nullable=True)         # YouTube | Instagram
    content_type = Column(String(20), nullable=True)     # Short | Long-form | Reel | Post
    topics = Column(JSONB, nullable=True)                # list[str]
    strategy = Column(String(30), nullable=True)
    recommended_slot = Column(JSONB, nullable=True)      # {weekday, hour_bucket, lift, ...}
    prediction = Column(JSONB, nullable=True)            # Prediction.to_dict()
    kit = Column(JSONB, nullable=True)                   # production kit from "Generate Next Project"
    enrichment_status = Column(String(20), nullable=True)  # None | queued | done | failed | skipped

    # Temporal (server-side timestamps — never naive datetimes into timestamptz)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=func.now())

    # Relationships
    creator = relationship("CreatorProfile", backref="content_suggestions")
    trend = relationship("PlatformTrend", backref="content_suggestions")

    def __repr__(self):
        return f"<ContentSuggestion(creator={self.creator_id}, status={self.status}, title={self.title[:40]})>"
