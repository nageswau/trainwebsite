"""hrc-006 -- vacancy co-ownership: job_assignments (the placement-officer owner and collaborators) and job_assignment_history.

Revision ID: 0261_job_assignments
Revises: 0258_vacancy_fields

docs/superpowers/specs/2026-11-04-hrc-006-vacancy-co-ownership-design.md (DEC-SCOPE-384 O1/O2). Additive: no existing row changes. 0001
builds a fresh database from the current models, which already carry the tables, so they are created only when missing (0222's idiom).
The upgrade backfills one "added primary" history row (reason `backfill`, no actor, at the job's created_at) per job with a recruiter;
NOT EXISTS keeps a re-run harmless. CHECKS is a frozen copy of the model's JOB_ASSIGNMENT_CHECKS at this revision.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0261_job_assignments"
down_revision = "0258_vacancy_fields"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {
    "ck_job_assignments_role": "role IN ('placement_officer', 'collaborator')",
    "ck_job_assignment_history_role": "role IN ('primary', 'placement_officer', 'collaborator')",
    "ck_job_assignment_history_action": "action IN ('added', 'removed')",
    "ck_job_assignment_history_reason": "reason IS NULL OR reason IN ('reassign', 'deactivated', 'backfill')",
}
BACKFILL = """
INSERT INTO job_assignment_history (id, job_id, user_id, role, action, reason, changed_by_user_id, created_at)
SELECT gen_random_uuid(), j.id, j.assigned_recruiter_user_id, 'primary', 'added', 'backfill', NULL, j.created_at
FROM jobs j
WHERE j.assigned_recruiter_user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM job_assignment_history h WHERE h.job_id = j.id AND h.reason = 'backfill')
"""


def _checks(prefix: str) -> list[sa.CheckConstraint]:
    return [sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items() if name.startswith(prefix)]


def upgrade() -> None:
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "job_assignments" not in tables:
        op.create_table(
            "job_assignments",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("added_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("job_id", "user_id", name="uq_job_assignments_job_user"),
            *_checks("ck_job_assignments_"),
        )
        op.create_index("ix_job_assignments_user_job", "job_assignments", ["user_id", "job_id"])
        op.create_index("uq_job_assignments_officer", "job_assignments", ["job_id"], unique=True, postgresql_where=sa.text("role = 'placement_officer'"))
    if "job_assignment_history" not in tables:
        op.create_table(
            "job_assignment_history",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("action", sa.String(10), nullable=False),
            sa.Column("reason", sa.String(20), nullable=True),
            sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *_checks("ck_job_assignment_history_"),
        )
        op.create_index("ix_job_assignment_history_job", "job_assignment_history", ["job_id", "created_at"])
    op.execute(BACKFILL)


def downgrade() -> None:
    """Refuses while owners or user-made history exist: ownership is not dropped silently (the backfill alone can be rebuilt)."""
    recorded = "SELECT 1 FROM job_assignments UNION ALL SELECT 1 FROM job_assignment_history WHERE reason IS DISTINCT FROM 'backfill' LIMIT 1"
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(recorded)).first():
        raise RuntimeError("Cannot downgrade 0261: requirement owners or ownership history exist (hrc-006)")
    op.drop_index("ix_job_assignment_history_job", table_name="job_assignment_history")
    op.drop_table("job_assignment_history")
    op.drop_index("uq_job_assignments_officer", table_name="job_assignments")
    op.drop_index("ix_job_assignments_user_job", table_name="job_assignments")
    op.drop_table("job_assignments")
