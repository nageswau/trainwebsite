"""bdm-001 -- bdm_profiles (1:1 with a `bdm` user).

Revision ID: 0061_bdm_profiles
Revises: 0060_agent_app_enrollment

docs/superpowers/specs/2026-10-02-bdm-001-bdm-profile-design.md §4 (DEC-SCOPE-055). Adds one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry this table, so creation is guarded (0055's
idiom). downgrade() refuses while profiles exist: they are the only record of each BDM's type and reporting manager.

Re-chained 2026-10-02 on merging `main` @ `e0395d6`: cut as `0058_bdm_profiles` on `0057_agent_applications`, but AGN-009's
`0058_agent_documents`, AGN-016's `0059_agent_tasks` and AGN-013's `0060_agent_app_enrollment` reached `main` first, so this
revision is now `0061_bdm_profiles` after 0060 (one head). A database stamped at `0058_bdm_profiles` is re-stamped with
`alembic stamp --purge 0057_agent_applications` then `upgrade head` (the guarded create makes the re-run harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0061_bdm_profiles"
down_revision = "0060_agent_app_enrollment"
branch_labels = None
depends_on = None

TABLE = "bdm_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bdm_type", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(40), nullable=False),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("department", sa.String(120), nullable=True),
        sa.Column("territory", sa.String(120), nullable=True),
        sa.Column("reporting_manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_bdm_profiles_user"),
        sa.CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_profiles_type"),
    )
    op.create_index("uq_bdm_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
    op.create_index("ix_bdm_profiles_reporting_manager", TABLE, ["reporting_manager_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0061_bdm_profiles: BDM profiles exist. Remove them deliberately first.")
    op.drop_table(TABLE)
