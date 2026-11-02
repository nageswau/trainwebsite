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


COLUMNS = (
    sa.Column("event_type", sa.String(80), nullable=True),
    sa.Column("entity_type", sa.String(50), nullable=True),
    sa.Column("entity_id", sa.String(80), nullable=True),
)


def upgrade() -> None:
    # 0001 builds a fresh database from the current models, which already carry these, so every step is guarded (0220's idiom; found
    # by itc-003: a fresh database stopped at this revision with "column event_type already exists").
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns("notifications")}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column("notifications", column)
    indexes = set() if inspector is None else {i["name"] for i in inspector.get_indexes("notifications")}
    if INDEX not in indexes:
        op.create_index(INDEX, "notifications", ["user_id", "read", "created_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="notifications")
    for name in ("entity_id", "entity_type", "event_type"):
        op.drop_column("notifications", name)
