"""AGN-003 -- per-staff optional permissions: Verify Documents and Reports (DEC-SCOPE-041 P1/P2).

Revision ID: 0048_agent_staff_permissions
Revises: 0047_agent_org_staff

docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md §5. Additive: two NOT NULL booleans on agent_org_members with
server default false, so every existing member reads false (existing staff lose Reports until a Master switches it on -- P1) and no
row is rewritten. A column is only added when missing, so a database created from the current models still upgrades. downgrade()
drops the two flags.
"""

import sqlalchemy as sa

from alembic import op

revision = "0048_agent_staff_permissions"
down_revision = "0047_agent_org_staff"
branch_labels = None
depends_on = None

FLAGS = ("can_verify_documents", "can_view_reports")


def _columns() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_org_members")}


def upgrade() -> None:
    existing = _columns()
    for name in FLAGS:
        if name not in existing:
            op.add_column("agent_org_members", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for name in reversed(FLAGS):
        op.drop_column("agent_org_members", name)
