"""upc-020 -- Partnership tasks + follow-ups.

Revision ID: 0124_partnership_tasks
Revises: 0123_candidate_consents

docs/superpowers/specs/2026-10-09-upc-020-partnership-tasks-design.md §2 (DEC-SCOPE-139). Adds `partnership_tasks`. 0001 builds a fresh
database from the current models, which already carry it, so the step is guarded. CHECKS repeats app.models (test_upc_020_migration).
No backfill: existing universities have no tasks. downgrade() refuses while any task exists: it would drop follow-ups and their history.

Re-chained 2026-10-09: drafted as `0123_partnership_tasks` on `0122_candidate_skills` (DEC-SCOPE-138, API §12BF, RBAC §2.64), but
rec-010's `0123_candidate_consents` merged first (main @ `6fc05526`), so this is `0124` (DEC-SCOPE-139, API §12BG, RBAC §2.65). A
database stamped at `0123_partnership_tasks` is re-stamped with `alembic stamp --purge 0122_candidate_skills`, then `upgrade head`
(every step here is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0124_partnership_tasks"
down_revision = "0123_candidate_consents"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {
    "ck_partnership_tasks_kind": "kind IN ('follow_up', 'task')",
    "ck_partnership_tasks_priority": "priority IN ('high', 'medium', 'low')",
    "ck_partnership_tasks_status": "status IN ('open', 'done', 'cancelled')",
    "ck_partnership_tasks_source": "source IN ('manual', 'stage', 'meeting', 'visit', 'agreement')",
    "ck_partnership_tasks_rule": "(source = 'manual') = (rule IS NULL)",
    "ck_partnership_tasks_completed": "(status = 'done') = (completed_at IS NOT NULL)",
    "ck_partnership_tasks_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
    "ck_partnership_tasks_cancel_reason": "cancel_reason IS NULL OR status = 'cancelled'",
}


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    if not op.get_context().as_sql and "partnership_tasks" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "partnership_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        _user_fk("assignee_user_id"),
        _user_fk("created_by_user_id"),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("rule", sa.String(80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_partnership_tasks_assignee_status_due", "partnership_tasks", ["assignee_user_id", "status", "due_on"])
    op.create_index("ix_partnership_tasks_university_status_due", "partnership_tasks", ["university_id", "status", "due_on"])
    op.create_index(
        "uq_partnership_tasks_open_rule", "partnership_tasks", ["university_id", "rule"], unique=True,
        postgresql_where=sa.text("status = 'open' AND rule IS NOT NULL"),
    )  # fmt: skip


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM partnership_tasks LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0124_partnership_tasks: partnership tasks exist. Remove them deliberately first.")
    op.drop_table("partnership_tasks")
