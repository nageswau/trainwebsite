"""itc-007 -- merge duplicate leads: enquiries.merged_at / merged_by_user_id.

Revision ID: 0225_lead_merge
Revises: 0224_tel_source_workload

docs/superpowers/specs/2026-11-02-itc-007-merge-duplicate-leads-design.md (DEC-SCOPE-340). Two nullable columns (every existing lead keeps
NULLs: never merged) and a CHECK: both set or neither, and only on a Duplicate. 0001 builds a fresh database from the current models,
which already carry them, so every step is guarded (0221's idiom). The downgrade drops them.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0225_lead_merge"
down_revision = "0224_tel_source_workload"
branch_labels = None
depends_on = None

CHECK = "ck_enquiries_merged"
CHECK_SQL = "(merged_at IS NULL) = (merged_by_user_id IS NULL) AND (merged_at IS NULL OR status = 'duplicate')"  # == models.LEAD_MERGED_CHECK
FK = "fk_enquiries_merged_by_user_id_users"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns("enquiries")}
    if "merged_at" not in columns:
        op.add_column("enquiries", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    if "merged_by_user_id" not in columns:
        op.add_column("enquiries", sa.Column("merged_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(FK, "enquiries", "users", ["merged_by_user_id"], ["id"], ondelete="RESTRICT")
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("enquiries")}
    if CHECK not in checks:
        op.create_check_constraint(CHECK, "enquiries", CHECK_SQL)


def downgrade() -> None:
    op.drop_constraint(CHECK, "enquiries", type_="check")
    op.drop_column("enquiries", "merged_by_user_id")  # drops its foreign key with it
    op.drop_column("enquiries", "merged_at")
