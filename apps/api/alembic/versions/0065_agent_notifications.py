"""AGN-017 -- notifications.dedupe_key (+ partial unique index) and partial indexes for the daily reminder queries.

Revision ID: 0065_agent_notifications
Revises: 0064_application_deposits

Drafted as 0061 after 0060; re-chained as 0064 after 0063 on merging main @ ff27fa4 (bdm-001, AGN-010, AGN-012 hold 0061-0063),
then as 0065 after 0064_application_deposits on merging main @ 3d9244f (AGN-011).

docs/superpowers/specs/2026-10-02-agn-017-notifications-design.md §5 (DEC-SCOPE-059). One nullable column and four partial indexes;
no existing row is read or written. 0001 builds a fresh database from the current models, which already carry them, so every add is
guarded (0057's idiom). downgrade() drops exactly what upgrade() added: the keys are derived reminder markers, not user data.
"""

import sqlalchemy as sa

from alembic import op

revision = "0065_agent_notifications"
down_revision = "0064_application_deposits"
branch_labels = None
depends_on = None

INDEXES = (
    ("ux_notifications_dedupe_key", "notifications", ["dedupe_key"], True, "dedupe_key IS NOT NULL"),
    ("ix_overseas_applications_agent_application_deadline", "overseas_applications", ["application_deadline"], False, "agent_student_id IS NOT NULL"),
    ("ix_overseas_applications_agent_offer_deadline", "overseas_applications", ["offer_deadline"], False, "agent_student_id IS NOT NULL"),
    ("ix_agent_tasks_open_due", "agent_tasks", ["due_at"], False, "status = 'open'"),
)


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or "dedupe_key" not in {c["name"] for c in inspector.get_columns("notifications")}:
        op.add_column("notifications", sa.Column("dedupe_key", sa.String(200), nullable=True))
    for name, table, columns, unique, where in INDEXES:
        if inspector is None or name not in {i["name"] for i in inspector.get_indexes(table)}:
            op.create_index(name, table, columns, unique=unique, postgresql_where=sa.text(where))


def downgrade() -> None:
    for name, table, *_ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_column("notifications", "dedupe_key")
