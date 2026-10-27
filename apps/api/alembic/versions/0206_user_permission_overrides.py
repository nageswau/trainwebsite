"""nehn-007 -- per-user permission overrides on top of the role grants.

Revision ID: 0206_user_permission_overrides
Revises: 0205_enquiry_list_indexes

docs/superpowers/specs/2026-10-27-nehn-007-per-user-permission-overrides-design.md (DEC-SCOPE-299). New table
`user_permission_overrides`: one allow/deny per (user, resource, action), a required reason and an optional expiry. 0001 builds a fresh
database from the current models, which already carry the table, so it is created only when missing (0196's idiom). No seed; no existing
row changes. The downgrade drops the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0206_user_permission_overrides"
down_revision = "0205_enquiry_list_indexes"
branch_labels = None
depends_on = None

TABLE = "user_permission_overrides"


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or TABLE not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("resource", sa.String(60), nullable=False),
            sa.Column("action", sa.String(20), nullable=False),
            sa.Column("effect", sa.String(10), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "resource", "action", name="uq_user_permission_overrides_user_key"),
            sa.CheckConstraint("effect IN ('allow', 'deny')", name="ck_user_permission_overrides_effect"),
        )
        op.create_index("ix_user_permission_overrides_user_id", TABLE, ["user_id"])


def downgrade() -> None:
    op.drop_table(TABLE)
