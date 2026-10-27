"""nehn-008 -- the `field.financial.view` grant: a report's financial columns follow the permission engine.

Revision ID: 0207_field_financial_grant
Revises: 0206_user_permission_overrides

docs/superpowers/specs/2026-10-27-nehn-008-field-column-policy-design.md (DEC-SCOPE-300). Seed only: SEED is a frozen copy of the new
`rbac.DEFAULT_GRANTS` keys at this revision -- today's partnership commission readers (upc-001 U2), so no report changes on upgrade. A row
that is already there (re-run) is left alone. No existing row changes. The downgrade deletes every `field.financial` grant and override.
"""

import sqlalchemy as sa

from alembic import op

revision = "0207_field_financial_grant"
down_revision = "0206_user_permission_overrides"
branch_labels = None
depends_on = None

SEED = (("partnership_manager", "field.financial", "view"), ("partnership_head", "field.financial", "view"))


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'field.financial'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'field.financial'")
