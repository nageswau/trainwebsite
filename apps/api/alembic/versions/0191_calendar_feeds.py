"""ccrm-038 -- the counselor's iCal feed token (hash only) and the appointment's calendar SEQUENCE.

Revision ID: 0191_calendar_feeds
Revises: 0190_overdue_escalation

docs/superpowers/specs/2026-10-25-ccrm-038-calendar-integration-design.md (DEC-SCOPE-273 CA2, CA4). 0001 builds a fresh database from the
current models, which already carry both, so each is added only when missing (0181's idiom). Existing appointments start at SEQUENCE 0.
The downgrade drops the table (every feed link stops working) and the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0191_calendar_feeds"
down_revision = "0190_overdue_escalation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or "calendar_feeds" not in inspector.get_table_names():
        op.create_table(
            "calendar_feeds",
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("token_hash", name="uq_calendar_feeds_token_hash"),
        )
    if offline or "calendar_sequence" not in {c["name"] for c in inspector.get_columns("appointments")}:
        op.add_column("appointments", sa.Column("calendar_sequence", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS calendar_feeds")
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS calendar_sequence")
