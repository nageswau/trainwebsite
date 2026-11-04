"""hrc-008 -- vacancy visibility: `jobs.visibility` (internal, portal, segment, public), `jobs.segment_pool_id`, the (status, visibility)
index and the first `jobs.publish` holder.

Revision ID: 0260_job_visibility
Revises: 0259_candidate_ownership

docs/superpowers/specs/2026-11-04-hrc-008-vacancy-visibility-design.md (DEC-SCOPE-383). 0001 builds a fresh database from the current
models, which already carry the columns, so each step runs only when missing (0257's idiom). The server default fills every existing job
with `public` (V3: no current listing disappears). The constants are frozen copies of the models / rbac at this revision
(test_hrc_008_migration). The downgrade drops what this revision added, including the grant.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0260_job_visibility"
down_revision = "0259_candidate_ownership"
branch_labels = None
depends_on = None

VISIBILITIES = ("internal", "portal", "segment", "public")
VISIBILITY_CHECK = "visibility IN ('internal', 'portal', 'segment', 'public')"
SEGMENT_CHECK = "(visibility = 'segment') = (segment_pool_id IS NOT NULL)"
SEED = (("placement_manager", "jobs", "publish"),)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("jobs")}
    if "visibility" not in existing:
        op.add_column("jobs", sa.Column("visibility", sa.String(10), nullable=False, server_default=sa.text("'public'")))
    if "segment_pool_id" not in existing:
        op.add_column("jobs", sa.Column("segment_pool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("talent_pools.id", ondelete="RESTRICT"), nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("jobs")}
    if "ck_jobs_visibility" not in checks:
        op.create_check_constraint("ck_jobs_visibility", "jobs", VISIBILITY_CHECK)
    if "ck_jobs_segment_pool" not in checks:
        op.create_check_constraint("ck_jobs_segment_pool", "jobs", SEGMENT_CHECK)
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_status_visibility ON jobs (status, visibility)")
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE role = 'placement_manager' AND resource = 'jobs' AND action = 'publish'")
    op.execute("DROP INDEX IF EXISTS ix_jobs_status_visibility")
    op.drop_constraint("ck_jobs_segment_pool", "jobs", type_="check")
    op.drop_constraint("ck_jobs_visibility", "jobs", type_="check")
    op.drop_column("jobs", "segment_pool_id")
    op.drop_column("jobs", "visibility")
