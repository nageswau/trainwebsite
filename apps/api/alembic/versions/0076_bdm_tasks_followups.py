"""bdm-008 (DEC-SCOPE-074): follow-ups and tasks -- notes, cancelled_at and cancel_reason on bdm_tasks.

Rows bdm-007 already cancelled (the meeting report's follow-up date was cleared) get their time and reason, so "cancelled <=> a
cancellation time" holds for every row. Additive: no column is dropped or retyped.

Revision ID: 0076_bdm_tasks_followups
Revises: 0075_telecaller_profiles
"""

import sqlalchemy as sa

from alembic import op

revision = "0076_bdm_tasks_followups"
down_revision = "0075_telecaller_profiles"
branch_labels = None
depends_on = None

TASKS = "bdm_tasks"
REPORT_CLEARED = "Follow-up date removed from the meeting report"  # = services.bdm_appointments.FOLLOW_UP_CLEARED
CHECKS = {
    "ck_bdm_tasks_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
    "ck_bdm_tasks_cancel_reason": "cancel_reason IS NULL OR status = 'cancelled'",
}
# Set-based and idempotent, so it also runs when 0001's create_all already built the columns.
BACKFILL = f"UPDATE {TASKS} SET cancelled_at = updated_at, cancel_reason = '{REPORT_CLEARED}' WHERE status = 'cancelled' AND cancelled_at IS NULL"


def _built_by_models() -> bool:
    if op.get_context().as_sql:
        return False
    return "cancelled_at" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TASKS)}


def upgrade() -> None:
    fresh = _built_by_models()
    if not fresh:
        op.add_column(TASKS, sa.Column("notes", sa.String(2000), nullable=True))
        op.add_column(TASKS, sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(TASKS, sa.Column("cancel_reason", sa.String(500), nullable=True))
    op.execute(BACKFILL)
    if not fresh:
        for name, sql in CHECKS.items():
            op.create_check_constraint(name, TASKS, sql)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TASKS} WHERE source = 'manual' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0076_bdm_tasks_followups: manual tasks exist. Remove them deliberately first.")
    for name in CHECKS:
        op.drop_constraint(name, TASKS, type_="check")
    for column in ("cancel_reason", "cancelled_at", "notes"):
        op.drop_column(TASKS, column)
