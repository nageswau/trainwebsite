"""AGN-003 -- per-staff optional permissions: Verify Documents and Reports (DEC-SCOPE-044 P1/P2).

Revision ID: 0052_agent_staff_permissions
Revises: 0051_school_bulk_uploads

docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md §5. Additive: two NOT NULL booleans on agent_org_members with
server default false, so every existing member reads false (existing staff lose Reports until a Master switches it on -- P1) and no
row is rewritten. A column is only added when missing, so a database created from the current models still upgrades. downgrade()
drops the two flags.

Re-chained 2026-10-01 on merging `main`: drafted as `0048_agent_staff_permissions` after `0047_agent_org_staff`, but `main` had
meanwhile chained ENH-030 `0048_school_attendance_records` -> AGN-004 `0049_agent_students_crm` -> ENH-014
`0050_notification_channels` after 0047, so this revision followed 0050 as `0051_agent_staff_permissions`. A second merge brought
ENH-028 `0051_school_bulk_uploads` (also after 0050), so it is now `0052_agent_staff_permissions` after it (one head). A database
stamped at an old id is re-stamped by `alembic stamp` (the add-if-missing upgrade makes a re-run harmless).
"""

import sqlalchemy as sa

from alembic import op

revision = "0052_agent_staff_permissions"
down_revision = "0051_school_bulk_uploads"
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
