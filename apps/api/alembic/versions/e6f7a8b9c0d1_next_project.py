"""Generate Next Project: production kit + enrichment status on content_suggestions

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("content_suggestions", sa.Column("kit", postgresql.JSONB(), nullable=True))
    op.add_column("content_suggestions", sa.Column("enrichment_status", sa.String(20), nullable=True))
    # Trend freshness lookups for the generator
    op.create_index("ix_platform_trends_fetched_at", "platform_trends", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_trends_fetched_at", "platform_trends")
    op.drop_column("content_suggestions", "enrichment_status")
    op.drop_column("content_suggestions", "kit")
