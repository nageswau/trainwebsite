"""hrc-030 -- interview results and their release, the global release switch and the default `results.release` grant (HR Manager).

Revision ID: 0287_interview_results
Revises: 0285_job_revisions

docs/superpowers/specs/2026-11-05-hrc-030-result-release-design.md (DEC-SCOPE-409 R1/R4/R5). Two new tables; 0001 builds a fresh database
from the current models, which already carry them, so each is created only when missing (0277's idiom). CHECKS and SEED are frozen copies
of the model / `rbac` at this revision. No backfill: decisions made before this revision have no result and keep today's behaviour (R12).
The downgrade drops both tables and the `results.release` grant rows (with their overrides); no interview or application changes.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0287_interview_results"
down_revision = "0285_job_revisions"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_interview_results_outcome": "outcome IN ('selected', 'rejected')",
    "ck_interview_results_state": "state IN ('pending_approval', 'released')",
    "ck_interview_results_release_mode": "release_mode IS NULL OR release_mode IN ('auto', 'approval')",
    "ck_interview_results_message": "char_length(candidate_message) <= 1000",
    "ck_interview_results_released": "(state = 'released') = (released_at IS NOT NULL AND released_by_user_id IS NOT NULL AND release_mode IS NOT NULL AND candidate_message IS NOT NULL)",
}
SEED = (("hr_manager", "results", "release"),)
UUID = postgresql.UUID(as_uuid=True)


def _user(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "interview_results" not in tables:
        op.create_table(
            "interview_results",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("interview_id", UUID, sa.ForeignKey("interviews.id", ondelete="RESTRICT"), nullable=False, unique=True),
            sa.Column("application_id", UUID, sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("outcome", sa.String(10), nullable=False),
            sa.Column("is_final", sa.Boolean(), nullable=False),
            sa.Column("state", sa.String(20), nullable=False),
            sa.Column("candidate_message", sa.String(1000), nullable=True),
            sa.Column("release_mode", sa.String(10), nullable=True),
            _user("decided_by_user_id"),
            _user("released_by_user_id"),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("ix_interview_results_state", "interview_results", ["state", "created_at"])
        op.create_index("ix_interview_results_application", "interview_results", ["application_id"])
    if "result_release_settings" not in tables:
        op.create_table(
            "result_release_settings",
            sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
            sa.Column("auto_release", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    op.execute("INSERT INTO result_release_settings (id, auto_release) VALUES (1, false) ON CONFLICT DO NOTHING")
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'results' AND action = 'release'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'results' AND action = 'release'")
    op.drop_table("result_release_settings")
    op.drop_table("interview_results")
