import uuid
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base


class MetricSnapshot(Base):
    """
    Time-series metric snapshots for content posts.
    A new snapshot is created each time metrics are fetched,
    enabling trend analysis over time.
    """
    __tablename__ = "metric_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("content_posts.id"), nullable=False)
    captured_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    watch_time_hours = Column(Float, default=0.0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)

    # Relationships
    post = relationship("ContentPost", back_populates="metric_snapshots")

    def __repr__(self):
        return f"<MetricSnapshot(post_id={self.post_id}, views={self.views}, captured_at={self.captured_at})>"
