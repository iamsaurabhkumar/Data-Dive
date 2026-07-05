"""Add trend idempotency index

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-05 13:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create composite unique index to ensure idempotency when retrying tasks.
    # Same source, same url, same day = duplicate
    op.execute("""
        CREATE UNIQUE INDEX uq_trend_source_url_day 
        ON platform_trends (source, external_url, ((fetched_at AT TIME ZONE 'UTC')::date))
        WHERE external_url IS NOT NULL;
    """)

def downgrade() -> None:
    op.execute("DROP INDEX uq_trend_source_url_day;")
