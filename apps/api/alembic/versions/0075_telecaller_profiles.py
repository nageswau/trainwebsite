"""tel-001 -- telecaller_profiles (1:1 with a `telecaller` user).

Revision ID: 0075_telecaller_profiles
Revises: 0074_enquiry_bdm_attribution

docs/superpowers/specs/2026-10-05-tel-001-telecaller-roles-design.md §4 (DEC-SCOPE-073). Adds one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry this table, so creation is guarded (0061's idiom).
downgrade() refuses while profiles exist: they are the only record of each telecaller's team and reporting manager.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0075_telecaller_profiles"
down_revision = "0074_enquiry_bdm_attribution"
branch_labels = None
depends_on = None

TABLE = "telecaller_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(40), nullable=False),
        sa.Column("reporting_manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_telecaller_profiles_user"),
        sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_telecaller_profiles_team"),
    )
    op.create_index("uq_telecaller_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
    op.create_index("ix_telecaller_profiles_reporting_manager", TABLE, ["reporting_manager_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0075_telecaller_profiles: telecaller profiles exist. Remove them deliberately first.")
    op.drop_table(TABLE)
