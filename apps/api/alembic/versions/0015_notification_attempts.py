"""Add attempt_count to notification_deliveries (NOT-001).

Revision ID: 0015_notification_attempts
Revises: 0014_placement_profile_withdrawn

NOT-001-AC02: a failed send must never be silently dropped. DATA_MODEL.md #7.1 fixes only
the *mechanism* -- a retry-eligible state exists -- not the retry *policy* (attempt count/
backoff), which stays open (PRD_OPEN_ITEMS.md item 13) and is not invented here. This column
is that mechanism: every delivery attempt is counted, even though no automatic retry job is
built yet.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_notification_attempts"
down_revision = "0014_placement_profile_withdrawn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("notification_deliveries")}

    if "attempt_count" not in columns:
        op.add_column("notification_deliveries", sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("notification_deliveries", "attempt_count")
