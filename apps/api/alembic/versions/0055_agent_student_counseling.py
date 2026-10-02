"""AGN-006 -- agent_student_counseling.

Revision ID: 0055_agent_student_counseling
Revises: 0054_school_onboarding_bulk

docs/superpowers/specs/2026-10-01-agn-006-counseling-record-design.md §4 (DEC-SCOPE-048). Create-table only: no existing table is
altered and no existing row is read or written. Guarded like 0053/0054: on a fresh database 0001_initial's create_all() has already
built the table from the model. `downgrade()` refuses while any counseling record exists (the 0049 pattern), so no counseling data is
dropped by accident; otherwise it drops the empty table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0055_agent_student_counseling"
down_revision = "0054_school_onboarding_bulk"
branch_labels = None
depends_on = None

TABLE = "agent_student_counseling"
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")  # frozen copy: a migration never imports the models


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    currency_list = ", ".join(f"'{c}'" for c in CURRENCIES)
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_students.id"), nullable=False),
        sa.Column("counseling_completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("career_interest", sa.String(200), nullable=True),
        sa.Column("course_preference", sa.String(200), nullable=True),
        sa.Column("country_preference", sa.String(120), nullable=True),
        sa.Column("budget_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("budget_currency", sa.String(3), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_student_id", name="uq_agent_student_counseling_student"),
        sa.CheckConstraint(
            "counseling_completed = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
            name="ck_agent_student_counseling_completed",
        ),
        sa.CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="ck_agent_student_counseling_budget"),
        sa.CheckConstraint(f"budget_currency IS NULL OR budget_currency IN ({currency_list})", name="ck_agent_student_counseling_currency"),
        sa.CheckConstraint("(budget_amount IS NULL) = (budget_currency IS NULL)", name="ck_agent_student_counseling_budget_pair"),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0055_agent_student_counseling: counseling records exist. Remove them deliberately first.")
    op.drop_table(TABLE)
