"""ccrm-029 -- counselor tasks.

Revision ID: 0175_counselor_tasks
Revises: 0174_student_profiles

docs/superpowers/specs/2026-10-24-ccrm-029-counselor-tasks-design.md (DEC-SCOPE-250). A new table only; nothing is backfilled. 0001 builds
a fresh database from the current models, which already carry the table, so it is created only when missing (0166's idiom). CHECKS
repeats app.models.COUNSELOR_TASK_CHECKS (test_ccrm_029_migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0175_counselor_tasks"
down_revision = "0174_student_profiles"
branch_labels = None
depends_on = None

TABLE = "counselor_tasks"
CHECKS = {
    "ck_counselor_tasks_status": "status IN ('open', 'done', 'cancelled')",
    "ck_counselor_tasks_priority": "priority IN ('high', 'medium', 'low')",
    "ck_counselor_tasks_source": "source IN ('manual', 'rule')",
    "ck_counselor_tasks_one_link": "num_nonnulls(lead_id, student_user_id, application_id) <= 1",
}


def _missing() -> bool:
    return op.get_context().as_sql or TABLE not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _missing():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("counselor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(10), nullable=False, server_default=sa.text("'open'")),
        sa.Column("source", sa.String(10), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("rule_key", sa.String(60), nullable=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_counselor_tasks_counselor_status_due", TABLE, ["counselor_user_id", "status", "due_on"])


def downgrade() -> None:
    op.drop_table(TABLE)
