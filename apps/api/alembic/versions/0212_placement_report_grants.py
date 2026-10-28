"""nehn-016 -- the `reports.placement` grants: the recruiter's placement reports follow the permission engine.

Revision ID: 0212_placement_report_grants
Revises: 0211_student_access_rules

docs/superpowers/specs/2026-10-28-nehn-016-recruiter-training-progress-design.md (DEC-SCOPE-312). Seed only: SEED is a frozen copy of the
new `rbac.DEFAULT_GRANTS` keys at this revision -- recruiters, placement managers and IT admins (rows = opted-in IT students). A row that
is already there (re-run) is left alone. No existing row changes. The downgrade deletes every `reports.placement` grant and override.
"""

import sqlalchemy as sa

from alembic import op

revision = "0212_placement_report_grants"
down_revision = "0211_student_access_rules"
branch_labels = None
depends_on = None

SEED = (
    ("placement_team", "reports.placement", "view"), ("placement_team", "reports.placement", "download"),
    ("placement_manager", "reports.placement", "view"), ("placement_manager", "reports.placement", "download"),
    ("it_admin", "reports.placement", "view"), ("it_admin", "reports.placement", "download"),
)


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'reports.placement'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'reports.placement'")
