"""itc-014 -- discount requests (maker-checker) and the `discounts.approve` grant for the IT Admin.

Revision ID: 0245_fee_discount_requests
Revises: 0243_it_conversion

docs/superpowers/specs/2026-11-03-itc-014-discount-approval-design.md (DEC-SCOPE-363). One new table and one seeded grant; no existing
row changes. 0001 builds a fresh database from the current models, which already carry the table, so the create is guarded (0222's
idiom); the grant insert ignores a row that is already there. The downgrade drops the requests and every `discounts.approve` grant and
override (`discounts.add` is untouched).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0245_fee_discount_requests"
down_revision = "0243_it_conversion"
branch_labels = None
depends_on = None

TABLE = "fee_discount_requests"
SEED = (("it_admin", "discounts", "approve"),)  # a frozen copy of rbac.DEFAULT_GRANTS' new key at this revision


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or TABLE not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id"), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("amount > 0", name="ck_fee_discount_requests_amount"),
            sa.CheckConstraint("status IS NULL OR status IN ('pending', 'approved', 'rejected')", name="ck_fee_discount_requests_status"),
        )
        op.create_index("ix_fee_discount_requests_enrollment_id", TABLE, ["enrollment_id"])
        op.create_index("uq_fee_discount_requests_one_pending", TABLE, ["enrollment_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'discounts' AND action = 'approve'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'discounts' AND action = 'approve'")
    op.drop_table(TABLE)
