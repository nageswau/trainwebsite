"""nehn-031 -- the coordinator certificate workflow: `certificate_rules`, `certificate_requests` and the new certificate grants.

Revision ID: 0203_certificate_workflow
Revises: 0202_learning_resource_files

docs/superpowers/specs/2026-10-27-nehn-031-coordinator-certificate-workflow-design.md (DEC-SCOPE-296). 0001 builds a fresh database from the
current models, which already carry both tables, so they are created only when missing (0194's idiom). The rules row is seeded with the
thresholds that were hardcoded before (100 / 75), so eligibility does not change on upgrade. SEED is a frozen copy of the new
`rbac.DEFAULT_GRANTS` keys at this revision. No existing row changes: issued certificates stay as they are. The downgrade drops both
tables and deletes only these grants.
"""

import sqlalchemy as sa

from alembic import op

revision = "0203_certificate_workflow"
down_revision = "0202_learning_resource_files"
branch_labels = None
depends_on = None

SEED = (("coordinator", "certificates", "issue"), ("coordinator", "certificates", "override"), ("it_admin", "certificates", "configure"))


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "certificate_rules" not in tables:
        op.create_table(
            "certificate_rules",
            sa.Column("division", sa.String(20), primary_key=True),
            sa.Column("min_progress_percent", sa.Integer(), nullable=False),
            sa.Column("min_attendance_percent", sa.Integer(), nullable=False),
            sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            *_timestamps(),
            sa.CheckConstraint("division = 'it'", name="ck_certificate_rules_division"),
            sa.CheckConstraint("min_progress_percent BETWEEN 0 AND 100 AND min_attendance_percent BETWEEN 0 AND 100", name="ck_certificate_rules_percent"),
        )
    if "certificate_requests" not in tables:
        op.create_table(
            "certificate_requests",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("recommended_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("certificate_id", sa.Uuid(), sa.ForeignKey("certificates.id", ondelete="SET NULL"), nullable=True),
            *_timestamps(),
            sa.CheckConstraint("status IN ('recommended', 'not_ready', 'issued')", name="ck_certificate_requests_status"),
        )
    op.execute("INSERT INTO certificate_rules (division, min_progress_percent, min_attendance_percent) VALUES ('it', 100, 75) ON CONFLICT DO NOTHING")
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("DELETE FROM role_permissions WHERE role = :role AND resource = :resource AND action = :action").bindparams(role=role, resource=resource, action=action))
    op.execute("DROP TABLE IF EXISTS certificate_requests")
    op.execute("DROP TABLE IF EXISTS certificate_rules")
