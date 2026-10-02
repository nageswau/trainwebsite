"""AGN-016 -- agent tasks and follow-ups (DEC-SCOPE-053).

Revision ID: 0059_agent_tasks
Revises: 0058_agent_documents

docs/superpowers/specs/2026-10-02-agn-016-tasks-followups-design.md §2. Creates one table; no existing table or row changes.
0001/0003 run Base.metadata.create_all from the CURRENT models, so a database built from scratch already has the table when this
runs: it is created only when missing (0056's idiom). downgrade() refuses while a task exists, then drops the table.

Re-chained 2026-10-02 on merging `main` @ `d371865`: drafted as `0058_agent_tasks` on 0057, but AGN-009's `0058_agent_documents` (also
on 0057) reached `main` first, so this revision is now `0059_agent_tasks` after 0058 (one head; AGENT_CRM_BACKLOG.md §6.2). A database
stamped at 0058_agent_tasks is re-stamped with `alembic stamp --purge 0057_agent_applications` then `upgrade head` (create-if-missing
makes the re-run harmless).
"""

import sqlalchemy as sa

from alembic import op

revision = "0059_agent_tasks"
down_revision = "0058_agent_documents"
branch_labels = None
depends_on = None

TABLE = "agent_tasks"
STUDENT_INDEX = "ix_agent_tasks_student_status_due"


def _tables() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_student_id", sa.Uuid(), sa.ForeignKey("agent_students.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'done', 'cancelled')", name="ck_agent_tasks_status"),
        sa.CheckConstraint("(status = 'open') = (closed_at IS NULL) AND (closed_at IS NULL) = (closed_by_user_id IS NULL)", name="ck_agent_tasks_closed"),
    )
    op.create_index(STUDENT_INDEX, TABLE, ["agent_student_id", "status", "due_at"])
    op.create_index("ix_agent_tasks_application_id", TABLE, ["application_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0059_agent_tasks: agent tasks exist. Remove them deliberately first.")
    op.drop_table(TABLE)
