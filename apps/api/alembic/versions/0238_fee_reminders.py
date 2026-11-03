"""itc-016 -- the fee-reminder schedule, the reminder log and the sweep's payments index.

Revision ID: 0238_fee_reminders
Revises: 0237_hr_review_tasks

docs/superpowers/specs/2026-11-03-itc-016-fee-reminders-design.md (DEC-SCOPE-357). Two new tables and one index on `payments`; no
existing row changes ("overdue" stays derived). 0001 builds a fresh database from the current models, which already carry them, so each
step is guarded (0222's idiom). The downgrade drops the reminder history with the tables (it is a log, nothing references it).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0238_fee_reminders"
down_revision = "0237_hr_review_tasks"
branch_labels = None
depends_on = None

LOG, SETTINGS, INDEX = "fee_reminder_log", "fee_reminder_settings", "ix_payments_status_due_date"


def _offline() -> bool:
    return op.get_context().as_sql


def upgrade() -> None:
    inspector = None if _offline() else sa.inspect(op.get_bind())
    tables = set() if inspector is None else set(inspector.get_table_names())
    if SETTINGS not in tables:
        op.create_table(
            SETTINGS,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("days_before", sa.Integer, nullable=False),
            sa.Column("overdue_days", sa.JSON, nullable=False),
            sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_fee_reminder_settings_one_row"),
            sa.CheckConstraint("days_before BETWEEN 0 AND 30", name="ck_fee_reminder_settings_days_before"),
        )
    if LOG not in tables:
        op.create_table(
            LOG,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("offset_days", sa.Integer, nullable=False),
            sa.Column("reminder_date", sa.Date, nullable=False),
            sa.Column("due_date", sa.Date, nullable=False),
            sa.Column("counselor_notified", sa.Boolean, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("payment_id", "kind", "offset_days", "reminder_date", name="uq_fee_reminder_log_rule_day"),
            sa.CheckConstraint("kind IN ('due_soon', 'overdue')", name="ck_fee_reminder_log_kind"),
        )
    if inspector is None or INDEX not in {i["name"] for i in inspector.get_indexes("payments")}:
        op.create_index(INDEX, "payments", ["status", "due_date"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="payments")
    op.drop_table(LOG)
    op.drop_table(SETTINGS)
