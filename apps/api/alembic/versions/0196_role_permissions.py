"""nehn-005 -- the role_permissions grant table behind `deps.require_permission`, seeded with today's behaviour.

Revision ID: 0196_role_permissions
Revises: 0195_agent_student_codes

docs/superpowers/specs/2026-10-26-nehn-005-permission-engine-design.md (DEC-SCOPE-281 P3/P8). 0001 builds a fresh database from the
current models, which already carry the table (empty), so it is created only when missing (0192's idiom); the seed is inserted either
way. SEED is a frozen copy of `rbac.DEFAULT_GRANTS` at this revision: the grants the pilot routes' inline checks
gave (admin payments: it_admin/overseas_admin; telecaller reports: also telecaller_manager). super_admin holds everything in code and has
no rows. No existing row changes. The downgrade drops the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0196_role_permissions"
down_revision = "0195_agent_student_codes"
branch_labels = None
depends_on = None

_PAYMENT_ADMIN = ("payments.view", "payments.add", "discounts.add")
_TELECALLER_REPORTS = ("reports.telecaller.view", "reports.telecaller.download")
SEED = {
    "it_admin": _PAYMENT_ADMIN + _TELECALLER_REPORTS,
    "overseas_admin": _PAYMENT_ADMIN + _TELECALLER_REPORTS,
    "telecaller_manager": _TELECALLER_REPORTS,
}


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "role_permissions" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "role_permissions",
            sa.Column("role", sa.String(50), primary_key=True),
            sa.Column("resource", sa.String(60), primary_key=True),
            sa.Column("action", sa.String(20), primary_key=True),
            sa.Column("granted_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    grants = sa.table("role_permissions", sa.column("role", sa.String), sa.column("resource", sa.String), sa.column("action", sa.String))
    rows = []
    for role, keys in SEED.items():
        for key in keys:
            resource, action = key.rsplit(".", 1)
            rows.append({"role": role, "resource": resource, "action": action})
    op.bulk_insert(grants, rows)


def downgrade() -> None:
    op.drop_table("role_permissions")
