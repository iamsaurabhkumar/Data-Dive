import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base


class CreatorProfile(Base):
    """
    Creator profiles linked to Supabase auth.users.
    Stores platform connection status and identifiers.
    """
    __tablename__ = "creator_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    youtube_connected = Column(Boolean, default=False)
    youtube_channel_id = Column(String, nullable=True)
    instagram_connected = Column(Boolean, default=False)
    instagram_user_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    # Relationships
    content_posts = relationship("ContentPost", back_populates="creator", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CreatorProfile(id={self.id}, user_id={self.user_id})>"
