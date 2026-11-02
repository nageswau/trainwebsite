"""itc-002 -- notification event type and record link.

Revision ID: 0221_notification_event_type
Revises: 0220_program_syllabus_image

DEC-SCOPE-336. Three nullable columns on `notifications` (every existing row keeps NULLs: an untyped, unlinked notice, as before) and
the inbox index `(user_id, read, created_at)` that GET /workflows/notifications and the unread count read. The downgrade drops both.
"""

import sqlalchemy as sa

from alembic import op

revision = "0221_notification_event_type"
down_revision = "0220_program_syllabus_image"
branch_labels = None
depends_on = None

INDEX = "ix_notifications_user_read_created"


def upgrade() -> None:
    op.add_column("notifications", sa.Column("event_type", sa.String(80), nullable=True))
    op.add_column("notifications", sa.Column("entity_type", sa.String(50), nullable=True))
    op.add_column("notifications", sa.Column("entity_id", sa.String(80), nullable=True))
    op.create_index(INDEX, "notifications", ["user_id", "read", "created_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="notifications")
    for name in ("entity_id", "entity_type", "event_type"):
        op.drop_column("notifications", name)
