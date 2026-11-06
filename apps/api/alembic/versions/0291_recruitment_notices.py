"""hrc-032 (DEC-SCOPE-412 N6/N7/N10): the two once-only markers and the `notifications.retry` grant.

Interviews already past the grace period and jobs already open are stamped, so the first sweep tells nobody about old records. Only the new
columns are written; existing data is otherwise untouched.

Revision ID: 0291_recruitment_notices
Revises: 0290_contact_status
"""

import sqlalchemy as sa

from alembic import op

revision = "0291_recruitment_notices"
down_revision = "0290_contact_status"
branch_labels = None
depends_on = None

SEED = (("hr_manager", "notifications", "retry"), ("placement_manager", "notifications", "retry"))
COLUMNS = (("interviews", "overdue_notified_at"), ("jobs", "match_notified_at"))


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    for table, column in COLUMNS:
        if offline or column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE interviews SET overdue_notified_at = now() WHERE overdue_notified_at IS NULL AND COALESCE(ends_at, scheduled_at) < now() - interval '24 hours'")
    op.execute("UPDATE jobs SET match_notified_at = now() WHERE match_notified_at IS NULL AND status IN ('requirement_received', 'sourcing', 'shortlisting', 'profiles_shared', 'interviewing')")
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("DELETE FROM role_permissions WHERE role = :role AND resource = :resource AND action = :action").bindparams(role=role, resource=resource, action=action))
    for table, column in COLUMNS:
        op.drop_column(table, column)
