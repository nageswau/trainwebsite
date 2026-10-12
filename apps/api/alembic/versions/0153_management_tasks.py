"""mgmt-028 -- the management to-do: management_tasks.

Revision ID: 0153_management_tasks
Revises: 0152_management_discussions

docs/superpowers/specs/2026-10-12-mgmt-028-management-tasks-design.md §3. A new table only; no existing row changes. 0001 builds a
fresh database from the current models, which already carry this table, so it is created only when missing (0122's idiom).
downgrade() refuses while any task exists: assigned management tasks are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0153_management_tasks"
down_revision = "0152_management_discussions"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
# Frozen copies of app.models.TASK_STATUSES / TASK_PRIORITIES / TASK_SOURCES.
STATUSES = ("open", "in_progress", "completed", "cancelled")
PRIORITIES = ("high", "medium", "low")
SOURCES = ("manual", "decision", "meeting", "plan")


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "management_tasks" in existing:
        return
    op.create_table(
        "management_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        _user("owner_user_id"),
        sa.Column("priority", sa.String(8), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), server_default=sa.text("'open'"), nullable=False),
        sa.Column("source", sa.String(10), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _user("created_by_user_id"),
        _user("updated_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_management_tasks_status"),
        sa.CheckConstraint(_in("priority", PRIORITIES), name="ck_management_tasks_priority"),
        sa.CheckConstraint(_in("source", SOURCES), name="ck_management_tasks_source"),
    )
    op.create_index("ix_management_tasks_owner_deadline_status", "management_tasks", ["owner_user_id", "deadline", "status"])
    op.create_index("ix_management_tasks_status_deadline", "management_tasks", ["status", "deadline"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM management_tasks LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0153_management_tasks: tasks exist. Clear them deliberately first.")
    op.drop_table("management_tasks")
