"""Add pgvector extension and V2 trend engine tables

Revision ID: a1b2c3d4e5f6
Revises: bd7ae62f3d1b
Create Date: 2026-07-05 12:50:00.000000

This migration:
1. Enables the pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
2. Creates platform_trends table with Vector(1536) column
3. Creates content_suggestions table with CASCADE/SET NULL FK constraints
4. Creates HNSW index on platform_trends.embedding for cosine similarity

IMPORTANT: The extension must be created BEFORE any table that uses the vector type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bd7ae62f3d1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ────────────────────────────────────────────────
    # Step 1: Enable pgvector extension
    # Must happen first. IF NOT EXISTS is idempotent.
    # Supabase has this pre-available on all tiers.
    # ────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ────────────────────────────────────────────────
    # Step 2: Create platform_trends table
    # Stores raw trending data + OpenAI embeddings
    # ────────────────────────────────────────────────
    op.create_table(
        'platform_trends',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('external_url', sa.Text(), nullable=True),
        sa.Column('raw_metadata', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Standard B-tree indexes for filtered queries
    op.create_index('ix_platform_trends_source', 'platform_trends', ['source'])
    op.create_index('ix_platform_trends_category', 'platform_trends', ['category'])

    # ────────────────────────────────────────────────
    # Step 3: HNSW index for vector cosine similarity
    # m=16: max connections per graph node
    # ef_construction=64: build-time candidate list size
    # vector_cosine_ops: enables the <=> operator
    # ────────────────────────────────────────────────
    op.execute("""
        CREATE INDEX ix_platform_trends_embedding_hnsw
        ON platform_trends
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # ────────────────────────────────────────────────
    # Step 4: Create content_suggestions table
    # AI-generated recommendations linked to creators
    # ────────────────────────────────────────────────
    op.create_table(
        'content_suggestions',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('creator_id', sa.UUID(), nullable=False),
        sa.Column('trend_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True, default=0.0),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),

        # GDPR: Delete creator profile → cascade-delete all their suggestions
        sa.ForeignKeyConstraint(
            ['creator_id'], ['creator_profiles.id'],
            ondelete='CASCADE',
        ),

        # TTL-safe: Delete expired trend → nullify the reference, keep the suggestion card
        sa.ForeignKeyConstraint(
            ['trend_id'], ['platform_trends.id'],
            ondelete='SET NULL',
        ),
    )

    # Indexes for common query patterns
    op.create_index('ix_content_suggestions_creator_id', 'content_suggestions', ['creator_id'])
    op.create_index('ix_content_suggestions_trend_id', 'content_suggestions', ['trend_id'])
    op.create_index('ix_content_suggestions_status', 'content_suggestions', ['status'])


def downgrade() -> None:
    op.drop_table('content_suggestions')
    op.drop_index('ix_platform_trends_embedding_hnsw', 'platform_trends')
    op.drop_table('platform_trends')
    # Note: We do NOT drop the vector extension on downgrade.
    # Other tables/extensions might depend on it.
