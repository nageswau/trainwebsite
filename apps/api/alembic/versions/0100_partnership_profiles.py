"""upc-001 -- partnership_profiles (1:1 with a `partnership_manager` user).

Revision ID: 0100_partnership_profiles
Revises: 0099_tel_settings

docs/superpowers/specs/2026-10-08-upc-001-partnership-roles-design.md §4 (DEC-SCOPE-116). Adds one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry this table, so creation is guarded (0061's idiom).
downgrade() refuses while profiles exist: they are the only record of each manager's Employee ID and reporting head.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0100_partnership_profiles"
down_revision = "0099_tel_settings"
branch_labels = None
depends_on = None

TABLE = "partnership_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("employee_id", sa.String(40), nullable=False),
        sa.Column("reporting_head_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_partnership_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
    op.create_index("ix_partnership_profiles_reporting_head", TABLE, ["reporting_head_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0100_partnership_profiles: partnership profiles exist. Remove them deliberately first.")
    op.drop_table(TABLE)
