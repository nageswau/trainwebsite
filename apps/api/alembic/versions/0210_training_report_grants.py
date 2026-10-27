"""nehn-009 -- the `reports.training` grants: the report library's training reports follow the permission engine.

Revision ID: 0210_training_report_grants
Revises: 0207_field_financial_grant

docs/superpowers/specs/2026-10-27-nehn-009-report-framework-design.md (DEC-SCOPE-303). Seed only: SEED is a frozen copy of the new
`rbac.DEFAULT_GRANTS` keys at this revision -- IT admins (every enrolment, as `/admin/enrollments`) and trainers (their own batches). A
row that is already there (re-run) is left alone. No existing row changes. The downgrade deletes every `reports.training` grant and override.
"""

import sqlalchemy as sa

from alembic import op

revision = "0210_training_report_grants"
down_revision = "0207_field_financial_grant"
branch_labels = None
depends_on = None

SEED = (
    ("it_admin", "reports.training", "view"), ("it_admin", "reports.training", "download"),
    ("trainer", "reports.training", "view"), ("trainer", "reports.training", "download"),
)


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'reports.training'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'reports.training'")
