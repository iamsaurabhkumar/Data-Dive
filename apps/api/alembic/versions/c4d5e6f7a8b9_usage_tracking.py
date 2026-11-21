"""Usage tracking: usage_events, feature_feedback, survey_prompts, telemetry opt-out

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-02 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("creator_profiles", sa.Column("telemetry_opt_out", sa.Boolean(), nullable=False, server_default="false"))

    op.create_table(
        "usage_events",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("action", sa.String(64), nullable=True),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("page", sa.String(120), nullable=True),
        sa.Column("client", sa.String(10), nullable=False, server_default="web"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_usage_events_creator_id", "usage_events", ["creator_id"])
    op.create_index("ix_usage_events_feature", "usage_events", ["feature"])
    op.create_index("ix_usage_events_ts", "usage_events", ["ts"])
    op.create_index("ix_usage_events_creator_feature_ts", "usage_events", ["creator_id", "feature", "ts"])

    op.create_table(
        "feature_feedback",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("worth_it", sa.String(10), nullable=False),
        sa.Column("improvement", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("trigger", sa.String(10), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        sa.CheckConstraint("worth_it IN ('yes','somewhat','no')", name="ck_feedback_worth"),
    )
    op.create_index("ix_feature_feedback_creator_id", "feature_feedback", ["creator_id"])
    op.create_index("ix_feature_feedback_feature", "feature_feedback", ["feature"])

    op.create_table(
        "survey_prompts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_survey_prompts_creator_id", "survey_prompts", ["creator_id"])

    # Supabase: these tables are server-written only — lock them down for the anon/authenticated roles.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
            EXECUTE 'ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE feature_feedback ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE survey_prompts ENABLE ROW LEVEL SECURITY';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("survey_prompts")
    op.drop_table("feature_feedback")
    op.drop_table("usage_events")
    op.drop_column("creator_profiles", "telemetry_opt_out")
