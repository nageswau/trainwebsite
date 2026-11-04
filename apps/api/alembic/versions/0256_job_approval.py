"""hrc-007 -- the vacancy approval workflow and the Filled status: job source and submission columns, the per-source approval settings,
the 13-status check and the first `jobs.approve` holder.

Revision ID: 0256_job_approval
Revises: 0251_candidate_compensation

docs/superpowers/specs/2026-11-04-hrc-007-vacancy-approval-design.md (DEC-SCOPE-380). 0001 builds a fresh database from the current
models, which already carry the columns and table, so each step runs only when missing (0222's idiom); the status check is always
replaced. Every constant here is a frozen copy of the models / rbac at this revision (test_hrc_007_migration). Backfill (A3): a job whose
"created" history row an employer user wrote is `employer`; one created as `requirement_received` (the legacy staff route's start) is
`legacy`; the rest keep the default `recruiter`. The downgrade moves `pending_approval` jobs back to `new` and `filled` ones to `closed`
(history rows are kept), restores the 11-status check, and drops what this revision added.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0256_job_approval"
down_revision = "0251_candidate_compensation"
branch_labels = None
depends_on = None

STATUSES = (
    "new",
    "pending_approval",
    "requirement_received",
    "sourcing",
    "shortlisting",
    "profiles_shared",
    "interviewing",
    "selected",
    "joined",
    "filled",
    "on_hold",
    "closed",
    "cancelled",
)
OLD_STATUSES = tuple(s for s in STATUSES if s not in ("pending_approval", "filled"))
STATUS_CHECK = "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")"
OLD_STATUS_CHECK = "status IN (" + ", ".join(f"'{s}'" for s in OLD_STATUSES) + ")"
SOURCES = ("recruiter", "employer", "legacy")
SOURCE_CHECK = "source IN ('recruiter', 'employer', 'legacy')"
SETTINGS = (("employer", True), ("recruiter", False), ("legacy", False))
SEED = (("hr_manager", "jobs", "approve"),)


def _columns() -> list[sa.Column]:
    return [
        sa.Column("source", sa.String(10), nullable=False, server_default=sa.text("'recruiter'")),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("jobs")}
    added_source = "source" not in existing
    for column in _columns():
        if column.name not in existing:
            op.add_column("jobs", column)
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("jobs")}
    if "ck_jobs_source" not in checks:
        op.create_check_constraint("ck_jobs_source", "jobs", SOURCE_CHECK)
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_status")
    op.create_check_constraint("ck_jobs_status", "jobs", STATUS_CHECK)
    if added_source:
        op.execute(
            "UPDATE jobs SET source = 'employer' WHERE id IN (SELECT h.job_id FROM job_status_history h JOIN users u ON u.id = h.changed_by_user_id "
            "WHERE h.from_status IS NULL AND u.role = 'employer')"
        )
        op.execute("UPDATE jobs SET source = 'legacy' WHERE source = 'recruiter' AND id IN (SELECT job_id FROM job_status_history WHERE from_status IS NULL AND to_status = 'requirement_received')")
    if offline or "job_approval_settings" not in set(inspector.get_table_names()):
        op.create_table(
            "job_approval_settings",
            sa.Column("source", sa.String(10), primary_key=True),
            sa.Column("required", sa.Boolean(), nullable=False),
            sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for source, required in SETTINGS:
        op.execute(sa.text("INSERT INTO job_approval_settings (source, required) VALUES (:source, :required) ON CONFLICT DO NOTHING").bindparams(source=source, required=required))
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE role = 'hr_manager' AND resource = 'jobs' AND action = 'approve'")
    op.drop_table("job_approval_settings")
    op.execute("UPDATE jobs SET status = 'new' WHERE status = 'pending_approval'")
    op.execute("UPDATE jobs SET status = 'closed' WHERE status = 'filled'")
    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_status", "jobs", OLD_STATUS_CHECK)
    op.drop_constraint("ck_jobs_source", "jobs", type_="check")
    for column in _columns():
        op.drop_column("jobs", column.name)
