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
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Float, DateTime, ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
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

    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("CreatorProfile", backref="content_suggestions")
    trend = relationship("PlatformTrend", backref="content_suggestions")

    def __repr__(self):
        return f"<ContentSuggestion(creator={self.creator_id}, status={self.status}, title={self.title[:40]})>"
