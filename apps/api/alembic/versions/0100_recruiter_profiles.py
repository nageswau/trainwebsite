"""rec-001 -- recruiter_profiles (1:1 with a `placement_team` user) + a profile for every existing recruiter.

Revision ID: 0100_recruiter_profiles
Revises: 0099_tel_settings

docs/superpowers/specs/2026-10-08-rec-001-recruiter-roles-design.md §3 (DEC-SCOPE-116). Adds one table and only inserts into it; no
existing row is changed. 0001 builds a fresh database from the current models, which already carry this table, so creation is guarded
(0061's idiom) -- but the backfill always runs: it is idempotent (one empty profile per `placement_team` user that has none, AC5).
downgrade() refuses while any profile carries an Employee ID or a manager; backfilled rows hold nothing and may be dropped.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0100_recruiter_profiles"
down_revision = "0099_tel_settings"
branch_labels = None
depends_on = None

TABLE = "recruiter_profiles"
BACKFILL = (
    f"INSERT INTO {TABLE} (id, user_id) SELECT gen_random_uuid(), u.id FROM users u "
    f"WHERE u.role = 'placement_team' AND NOT EXISTS (SELECT 1 FROM {TABLE} p WHERE p.user_id = u.id)"
)


def upgrade() -> None:
    if op.get_context().as_sql or TABLE not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("employee_id", sa.String(40), nullable=True),
            sa.Column("reporting_manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_recruiter_profiles_user"),
        )
        op.create_index("uq_recruiter_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
        op.create_index("ix_recruiter_profiles_reporting_manager", TABLE, ["reporting_manager_user_id"])
    op.execute(BACKFILL)


def downgrade() -> None:
    carrying = f"SELECT 1 FROM {TABLE} WHERE employee_id IS NOT NULL OR reporting_manager_user_id IS NOT NULL LIMIT 1"
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(carrying)).first():
        raise RuntimeError("Cannot downgrade 0100_recruiter_profiles: recruiter profiles carry an Employee ID or a manager. Remove them deliberately first.")
    op.drop_table(TABLE)
