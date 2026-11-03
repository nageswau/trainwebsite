"""itc-015 -- the fee adjustments ledger (credit notes, write-offs, refunds, payment reversals) and the `payments.refund` grant.

Revision ID: 0244_fee_adjustments
Revises: 0243_it_conversion

docs/superpowers/specs/2026-11-03-itc-015-fee-adjustments-design.md (DEC-SCOPE-362). One new table; no existing row changes. 0001 builds
a fresh database from the current models, which already carry the table, so it is created only when missing (0222's idiom). KINDS /
MODES are frozen copies of the model's tuples at this revision. The downgrade drops the table (a fresh ledger) and deletes only this grant.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0244_fee_adjustments"
down_revision = "0243_it_conversion"
branch_labels = None
depends_on = None

TABLE = "fee_adjustments"
KINDS = ("credit_note", "write_off", "refund", "reversal")
MODES = ("cash", "upi", "card", "bank_transfer", "cheque")
SEED = (("it_admin", "payments", "refund"),)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if TABLE not in tables:
        uuid = postgresql.UUID(as_uuid=True)
        op.create_table(
            TABLE,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("enrollment_id", uuid, sa.ForeignKey("enrollments.id"), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("applied_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("payment_mode", sa.String(20), nullable=True),
            sa.Column("reference", sa.String(160), nullable=True),
            sa.Column("payment_id", uuid, sa.ForeignKey("payments.id"), nullable=True),
            sa.Column("replacement_payment_id", uuid, sa.ForeignKey("payments.id"), nullable=True),
            sa.Column("document_no", sa.String(40), nullable=True, unique=True),
            sa.Column("approved_by_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(f"kind IN ({_in(KINDS)})", name="ck_fee_adjustments_kind"),
            sa.CheckConstraint("amount > 0", name="ck_fee_adjustments_amount"),
            sa.CheckConstraint("applied_amount >= 0 AND applied_amount <= amount", name="ck_fee_adjustments_applied"),
            sa.CheckConstraint(f"payment_mode IS NULL OR payment_mode IN ({_in(MODES)})", name="ck_fee_adjustments_mode"),
        )
        op.create_index("ix_fee_adjustments_enrollment_id", TABLE, ["enrollment_id"])
        op.create_index("uq_fee_adjustments_reversal", TABLE, ["payment_id"], unique=True, postgresql_where=sa.text("kind = 'reversal'"))
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("DELETE FROM role_permissions WHERE role = :role AND resource = :resource AND action = :action").bindparams(role=role, resource=resource, action=action))
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
