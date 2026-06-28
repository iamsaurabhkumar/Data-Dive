import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base


class ContentPost(Base):
    """
    Content posts from all connected platforms.
    Normalized to a common schema regardless of source platform.
    """
    __tablename__ = "content_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creator_profiles.id"), nullable=False)
    platform = Column(String(20), nullable=False)  # 'YouTube' | 'Instagram'
    external_post_id = Column(String(255), nullable=False)  # Platform's native ID
    title = Column(Text, nullable=False)
    content_type = Column(String(20), nullable=False)  # 'Short' | 'Long-form' | 'Reel' | 'Post'
    thumbnail_url = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    # Unique constraint: no duplicate posts from same platform
    __table_args__ = (
        UniqueConstraint("platform", "external_post_id", name="uq_platform_post"),
    )

    # Relationships
    creator = relationship("CreatorProfile", back_populates="content_posts")
    metric_snapshots = relationship("MetricSnapshot", back_populates="post", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ContentPost(platform={self.platform}, title={self.title[:30]})>"
