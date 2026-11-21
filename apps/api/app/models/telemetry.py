"""Usage events, feature feedback and survey prompt records."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class UsageEventRow(Base):
    __tablename__ = "usage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True)
    name = Column(String(40), nullable=False)
    feature = Column(String(40), nullable=False, index=True)
    action = Column(String(64), nullable=True)
    properties = Column(JSONB, nullable=True)
    page = Column(String(120), nullable=True)
    client = Column(String(10), nullable=False, server_default="web")
    duration_ms = Column(Integer, nullable=True)
    status = Column(Integer, nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class FeatureFeedbackRow(Base):
    __tablename__ = "feature_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    feature = Column(String(40), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    worth_it = Column(String(10), nullable=False)
    improvement = Column(Text, nullable=True)
    context = Column(JSONB, nullable=True)
    trigger = Column(String(10), nullable=False, server_default="manual")
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class SurveyPromptRow(Base):
    __tablename__ = "survey_prompts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    feature = Column(String(40), nullable=False)
    dismissed = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
