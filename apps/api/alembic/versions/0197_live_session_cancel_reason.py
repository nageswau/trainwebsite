"""nehn-029 -- `live_sessions.cancel_reason`, the trainer's reason for a cancelled live class.

Revision ID: 0197_live_session_cancel_reason
Revises: 0196_role_permissions

docs/superpowers/specs/2026-10-26-nehn-029-live-class-reschedule-cancel-design.md (DEC-SCOPE-283). `live_sessions.status` already exists
(default "scheduled"); only the reason is new. Nullable, no backfill: every existing session keeps its status and has no reason. 0001 builds
a fresh database from the current models, which already carry the column, so it is added only when missing (0195's idiom). The downgrade
drops the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0197_live_session_cancel_reason"
down_revision = "0196_role_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "cancel_reason" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("live_sessions")}:
        op.add_column("live_sessions", sa.Column("cancel_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("live_sessions", "cancel_reason")
