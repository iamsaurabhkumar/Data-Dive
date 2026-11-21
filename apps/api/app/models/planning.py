"""
Planning-bridge tables: Kanban production cards, their event history,
prediction reviews and per-creator calibration factors.
"""
import uuid

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ProductionCard(Base):
    __tablename__ = "production_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_id = Column(UUID(as_uuid=True), ForeignKey("content_suggestions.id", ondelete="SET NULL"), nullable=True)
    post_id = Column(UUID(as_uuid=True), ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True)

    title = Column(Text, nullable=False)
    hook = Column(Text, nullable=True)
    outline = Column(JSONB, nullable=True)
    platform = Column(String(20), nullable=False)
    content_type = Column(String(20), nullable=False)
    topics = Column(JSONB, nullable=True)
    strategy = Column(String(30), nullable=True)
    rationale = Column(Text, nullable=True)

    stage = Column(String(20), nullable=False, server_default="idea", index=True)
    position = Column(Integer, nullable=False, server_default="0")
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    prediction = Column(JSONB, nullable=True)
    recommended_slot = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=func.now())

    events = relationship("ProductionEvent", back_populates="card", cascade="all, delete-orphan")
    review = relationship("PredictionReview", back_populates="card", uselist=False, cascade="all, delete-orphan")


class ProductionEvent(Base):
    __tablename__ = "production_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    card_id = Column(UUID(as_uuid=True), ForeignKey("production_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage = Column(String(20), nullable=True)
    to_stage = Column(String(20), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    card = relationship("ProductionCard", back_populates="events")


class PredictionReview(Base):
    __tablename__ = "prediction_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    card_id = Column(UUID(as_uuid=True), ForeignKey("production_cards.id", ondelete="CASCADE"), nullable=False, unique=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = Column(UUID(as_uuid=True), ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True)

    verdict = Column(String(20), nullable=False)
    views_ratio = Column(Float, nullable=False)
    abs_pct_error = Column(Float, nullable=False)
    result = Column(JSONB, nullable=False)       # full ReviewResult
    reviewed_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    card = relationship("ProductionCard", back_populates="review")


class CreatorCalibration(Base):
    __tablename__ = "creator_calibrations"
    __table_args__ = (UniqueConstraint("creator_id", "platform", "content_type", name="uq_calibration_scope"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)
    content_type = Column(String(20), nullable=False)
    factor = Column(Float, nullable=False, server_default="1.0")
    samples = Column(Integer, nullable=False, server_default="0")
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=func.now())
