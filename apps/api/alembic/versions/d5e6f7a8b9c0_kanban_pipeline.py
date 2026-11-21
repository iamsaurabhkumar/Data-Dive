"""Kanban pipeline stages: idea → scripting → filming → editing → published (+ reviewed)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-03 12:00:00.000000

Maps existing cards/events: planning→scripting, production→filming, scheduled→editing.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORWARD = {"planning": "scripting", "production": "filming", "scheduled": "editing"}
NEW = "('idea','scripting','filming','editing','published','reviewed')"
OLD = "('idea','planning','production','scheduled','published','reviewed')"


def _remap(mapping: dict) -> None:
    for old, new in mapping.items():
        op.execute(f"UPDATE production_cards SET stage = '{new}' WHERE stage = '{old}'")
        op.execute(f"UPDATE production_events SET from_stage = '{new}' WHERE from_stage = '{old}'")
        op.execute(f"UPDATE production_events SET to_stage = '{new}' WHERE to_stage = '{old}'")


def upgrade() -> None:
    op.drop_constraint("ck_card_stage", "production_cards", type_="check")
    _remap(FORWARD)
    op.create_check_constraint("ck_card_stage", "production_cards", f"stage IN {NEW}")


def downgrade() -> None:
    op.drop_constraint("ck_card_stage", "production_cards", type_="check")
    _remap({v: k for k, v in FORWARD.items()})
    op.create_check_constraint("ck_card_stage", "production_cards", f"stage IN {OLD}")
