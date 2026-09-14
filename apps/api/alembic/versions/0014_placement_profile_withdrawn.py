"""Add withdrawn to placement_profiles (ADM-007).

Revision ID: 0014_placement_profile_withdrawn
Revises: 0013_question_threads

ADM-007-AC02: "A candidate withdrawn from the pool no longer appears in active
matching, but historical placement records are retained." No such concept existed --
`PlacementProfile.available` only ever meant "temporarily unavailable," not a
permanent withdrawal from the pool. Net-new column.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_placement_profile_withdrawn"
down_revision = "0013_question_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("placement_profiles")}

    if "withdrawn" not in columns:
        op.add_column("placement_profiles", sa.Column("withdrawn", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("placement_profiles", "withdrawn")
