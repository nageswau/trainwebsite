"""hrc-016 -- candidate notes and candidate tasks.

Revision ID: 0262_candidate_notes_tasks
Revises: 0261_job_assignments

docs/superpowers/specs/2026-11-04-hrc-016-candidate-notes-tasks-timeline-design.md (DEC-SCOPE-385 T1-T3). Additive: no existing row
changes. 0001 builds a fresh database from the current models, which already carry the tables, so they are created only when missing
(0222's idiom). CHECKS is a frozen copy of the model's CANDIDATE_NOTE_TASK_CHECKS at this revision.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0262_candidate_notes_tasks"
down_revision = "0261_job_assignments"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {
    "ck_candidate_notes_body": "char_length(body) BETWEEN 1 AND 2000",
    "ck_candidate_tasks_type": "task_type IN ('follow_up', 'resume_screening', 'interview_coordination', 'employer_feedback')",
    "ck_candidate_tasks_status": "status IN ('open', 'done', 'cancelled')",
    "ck_candidate_tasks_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)"
    ),
}


def _checks(prefix: str) -> list[sa.CheckConstraint]:
    return [sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items() if name.startswith(prefix)]


def _user(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "candidate_notes" not in tables:
        op.create_table(
            "candidate_notes",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
            _user("author_user_id"),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *_checks("ck_candidate_notes_"),
        )
        op.create_index("ix_candidate_notes_candidate_created", "candidate_notes", ["candidate_id", "created_at"])
    if "candidate_tasks" not in tables:
        op.create_table(
            "candidate_tasks",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("application_id", UUID, sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("task_type", sa.String(32), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            _user("assignee_user_id"),
            sa.Column("status", sa.String(16), server_default=sa.text("'open'"), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            _user("completed_by_user_id", nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            _user("cancelled_by_user_id", nullable=True),
            _user("created_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *_checks("ck_candidate_tasks_"),
        )
        op.create_index("ix_candidate_tasks_candidate", "candidate_tasks", ["candidate_id", "status", "due_at"])
        op.create_index("ix_candidate_tasks_assignee_open", "candidate_tasks", ["assignee_user_id", "due_at"], postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    """Refuses while notes or tasks exist: they are not dropped silently."""
    recorded = "SELECT 1 FROM candidate_notes UNION ALL SELECT 1 FROM candidate_tasks LIMIT 1"
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(recorded)).first():
        raise RuntimeError("Cannot downgrade 0262: candidate notes or tasks exist (hrc-016)")
    op.drop_index("ix_candidate_tasks_assignee_open", table_name="candidate_tasks")
    op.drop_index("ix_candidate_tasks_candidate", table_name="candidate_tasks")
    op.drop_table("candidate_tasks")
    op.drop_index("ix_candidate_notes_candidate_created", table_name="candidate_notes")
    op.drop_table("candidate_notes")
