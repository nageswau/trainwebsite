"""Add assigned_to_user_id and resolution_note to support_tickets (STU-005).

Revision ID: 0010_support_ticket_assignment
Revises: 0009_webinar_registrations

DATA_MODEL.md §4.5's own stated field ("assigned_to_user_id (nullable -- an unassigned
ticket stays visible and open, never hidden, STU-005-AC02)") did not exist on the
inherited `SupportTicket` table -- staff had no way to claim or resolve a ticket at all.
`resolution_note` is net-new, matching the same "reviewer notes" convention already used
for attendance-correction review and document verification (see `workflows.py`).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_support_ticket_assignment"
down_revision = "0009_webinar_registrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("support_tickets")}

    if "assigned_to_user_id" not in columns:
        op.add_column("support_tickets", sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
        op.create_index("ix_support_tickets_assigned_to_user_id", "support_tickets", ["assigned_to_user_id"])
    if "resolution_note" not in columns:
        op.add_column("support_tickets", sa.Column("resolution_note", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("support_tickets", "resolution_note")
    op.drop_index("ix_support_tickets_assigned_to_user_id", table_name="support_tickets")
    op.drop_column("support_tickets", "assigned_to_user_id")
