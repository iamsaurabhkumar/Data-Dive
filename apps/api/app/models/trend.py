"""
PlatformTrend model — stores raw trending data from external sources
alongside OpenAI embeddings for semantic similarity search.

Sources: YouTube trending, TikTok hashtags, Instagram Reels, NewsAPI.
Vector dimension: 1536 (OpenAI text-embedding-3-small, hardcoded).
Index: HNSW with vector_cosine_ops for high-recall ANN queries.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Float, DateTime, Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class PlatformTrend(Base):
    """
    Raw platform trend data with semantic embedding.

    The embedding column enables cosine similarity search against
    creator content history to find contextually relevant trends.
    """
    __tablename__ = "platform_trends"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source identification
    source = Column(String(30), nullable=False, index=True)       # youtube | tiktok | instagram | news
    category = Column(String(100), nullable=False, index=True)    # tech | gaming | fitness | etc.

    # Content
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    external_url = Column(Text, nullable=True)

    # Platform-specific raw data (view counts, hashtag metrics, etc.)
    raw_metadata = Column(JSONB, nullable=True)

    # OpenAI text-embedding-3-small — strictly 1536 dimensions
    embedding = Column(Vector(1536), nullable=True)

    # Temporal
    fetched_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # HNSW index for high-recall approximate nearest neighbor search
        # m=16: max connections per node (default, good balance of recall vs memory)
        # ef_construction=64: candidate list size during build (default, good recall)
        # vector_cosine_ops: enables the <=> cosine distance operator
        Index(
            "ix_platform_trends_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self):
        return f"<PlatformTrend(source={self.source}, title={self.title[:40]})>"
