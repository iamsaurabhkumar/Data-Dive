"""Phase 3 planning bridge: idea fields, production cards, reviews, calibrations, RLS

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-29 12:00:00.000000

1. content_suggestions gains analytics-driven idea columns (hook, outline, platform,
   content_type, topics, strategy, recommended_slot, prediction, source) and a
   server-side UUID default (the previous migration only set a client-side default).
2. New tables: production_cards, production_events, prediction_reviews, creator_calibrations.
3. Supabase hardening (only when the `auth` schema exists): RLS policies scoped to the
   signed-in creator on content_suggestions + the new tables, and Realtime publication
   for content_suggestions / production_cards.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ("content_suggestions", "production_cards", "prediction_reviews", "creator_calibrations")


def upgrade() -> None:
    # ---- 1. content_suggestions: idea columns + server default id ----------
    op.execute("ALTER TABLE content_suggestions ALTER COLUMN id SET DEFAULT gen_random_uuid();")
    op.execute("ALTER TABLE platform_trends ALTER COLUMN id SET DEFAULT gen_random_uuid();")
    op.add_column("content_suggestions", sa.Column("source", sa.String(30), nullable=False, server_default="trend"))
    op.add_column("content_suggestions", sa.Column("hook", sa.Text(), nullable=True))
    op.add_column("content_suggestions", sa.Column("outline", postgresql.JSONB(), nullable=True))
    op.add_column("content_suggestions", sa.Column("platform", sa.String(20), nullable=True))
    op.add_column("content_suggestions", sa.Column("content_type", sa.String(20), nullable=True))
    op.add_column("content_suggestions", sa.Column("topics", postgresql.JSONB(), nullable=True))
    op.add_column("content_suggestions", sa.Column("strategy", sa.String(30), nullable=True))
    op.add_column("content_suggestions", sa.Column("recommended_slot", postgresql.JSONB(), nullable=True))
    op.add_column("content_suggestions", sa.Column("prediction", postgresql.JSONB(), nullable=True))

    # ---- 2. planning tables ------------------------------------------------
    op.create_table(
        "production_cards",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_id", sa.UUID(), sa.ForeignKey("content_suggestions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("post_id", sa.UUID(), sa.ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("outline", postgresql.JSONB(), nullable=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("topics", postgresql.JSONB(), nullable=True),
        sa.Column("strategy", sa.String(30), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(20), nullable=False, server_default="idea"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prediction", postgresql.JSONB(), nullable=True),
        sa.Column("recommended_slot", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("stage IN ('idea','planning','production','scheduled','published','reviewed')", name="ck_card_stage"),
    )
    op.create_index("ix_production_cards_creator_id", "production_cards", ["creator_id"])
    op.create_index("ix_production_cards_stage", "production_cards", ["stage"])

    op.create_table(
        "production_events",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("card_id", sa.UUID(), sa.ForeignKey("production_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_stage", sa.String(20), nullable=True),
        sa.Column("to_stage", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_production_events_card_id", "production_events", ["card_id"])

    op.create_table(
        "prediction_reviews",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("card_id", sa.UUID(), sa.ForeignKey("production_cards.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.UUID(), sa.ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("views_ratio", sa.Float(), nullable=False),
        sa.Column("abs_pct_error", sa.Float(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_prediction_reviews_creator_id", "prediction_reviews", ["creator_id"])

    op.create_table(
        "creator_calibrations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("factor", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("creator_id", "platform", "content_type", name="uq_calibration_scope"),
    )
    op.create_index("ix_creator_calibrations_creator_id", "creator_calibrations", ["creator_id"])

    # ---- 3. Supabase-only hardening (no-op on plain Postgres) ---------------
    # Policies map the JWT user (auth.uid()) to creator_profiles.user_id; the service
    # role used by the API/worker bypasses RLS, so server-side code is unaffected.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth')
             AND EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                         WHERE n.nspname = 'auth' AND p.proname = 'uid') THEN
            EXECUTE 'ALTER TABLE content_suggestions ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE production_cards ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE prediction_reviews ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE creator_calibrations ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE production_events ENABLE ROW LEVEL SECURITY';

            EXECUTE 'DROP POLICY IF EXISTS creator_owns_rows ON content_suggestions';
            EXECUTE 'CREATE POLICY creator_owns_rows ON content_suggestions FOR ALL TO authenticated
                     USING (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))
                     WITH CHECK (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))';
            EXECUTE 'DROP POLICY IF EXISTS creator_owns_rows ON production_cards';
            EXECUTE 'CREATE POLICY creator_owns_rows ON production_cards FOR ALL TO authenticated
                     USING (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))
                     WITH CHECK (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))';
            EXECUTE 'DROP POLICY IF EXISTS creator_owns_rows ON prediction_reviews';
            EXECUTE 'CREATE POLICY creator_owns_rows ON prediction_reviews FOR SELECT TO authenticated
                     USING (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))';
            EXECUTE 'DROP POLICY IF EXISTS creator_owns_rows ON creator_calibrations';
            EXECUTE 'CREATE POLICY creator_owns_rows ON creator_calibrations FOR SELECT TO authenticated
                     USING (creator_id IN (SELECT id FROM creator_profiles WHERE user_id = auth.uid()))';
            EXECUTE 'DROP POLICY IF EXISTS creator_owns_rows ON production_events';
            EXECUTE 'CREATE POLICY creator_owns_rows ON production_events FOR SELECT TO authenticated
                     USING (card_id IN (SELECT c.id FROM production_cards c JOIN creator_profiles p ON p.id = c.creator_id
                                        WHERE p.user_id = auth.uid()))';
          END IF;

          IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
            BEGIN
              EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE content_suggestions';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END;
            BEGIN
              EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE production_cards';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("creator_calibrations")
    op.drop_table("prediction_reviews")
    op.drop_table("production_events")
    op.drop_table("production_cards")
    for col in ("prediction", "recommended_slot", "strategy", "topics", "content_type", "platform", "outline", "hook", "source"):
        op.drop_column("content_suggestions", col)
