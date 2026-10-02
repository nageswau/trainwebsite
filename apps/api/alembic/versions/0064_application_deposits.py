"""AGN-011 -- application deposits collected through Razorpay (DEC-SCOPE-058).

Revision ID: 0064_application_deposits
Revises: 0063_agent_visa_details

docs/superpowers/specs/2026-10-02-agn-011-deposit-collection-design.md §3. Creates one table; no existing table or row changes (deposit
payments are ordinary `payments` rows with `reference_type = 'agent_deposit'`). 0001/0003 run Base.metadata.create_all from the CURRENT
models, so a database built from scratch already has the table when this runs: it is created only when missing (0059's idiom).
downgrade() refuses while a deposit exists, then drops the table.

Re-chained 2026-10-03 on merging `main` @ `ff27fa4`: drafted as `0063_application_deposits` on 0062, but AGN-012's `0063_agent_visa_details`
(also on 0062) reached `main` first, so this revision is now `0064_application_deposits` after it (one head). A database stamped at
0063_application_deposits is re-stamped with `alembic stamp --purge 0062_agent_offer_details` then `upgrade head` (create-if-missing makes
the re-run harmless).
"""

import sqlalchemy as sa

from alembic import op

revision = "0064_application_deposits"
down_revision = "0063_agent_visa_details"
branch_labels = None
depends_on = None

TABLE = "application_deposits"
CHECKS = {
    "ck_application_deposits_status": "status IN ('not_required', 'pending', 'paid', 'remitted', 'refunded')",
    "ck_application_deposits_currency": "currency = 'INR'",
    "ck_application_deposits_required": "(status = 'not_required') = (NOT required)",
    "ck_application_deposits_amount": "(required AND amount IS NOT NULL AND amount > 0) OR (NOT required AND amount IS NULL AND due_date IS NULL)",
    "ck_application_deposits_paid": "(paid_payment_id IS NULL) = (status IN ('not_required', 'pending')) AND (paid_payment_id IS NULL) = (paid_at IS NULL)",
    "ck_application_deposits_remitted": "(remitted_at IS NULL) = (remittance_reference IS NULL)",
    "ck_application_deposits_refund": (
        "(refunded_at IS NULL) = (refund_amount IS NULL) AND (refunded_at IS NULL) = (refund_reason IS NULL) AND (refunded_at IS NULL) = (status <> 'refunded') AND (refund_amount IS NULL OR refund_amount > 0)"
    ),
}


def _tables() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_payment_id", sa.Uuid(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("paid_payment_id", sa.Uuid(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remitted_at", sa.Date(), nullable=True),
        sa.Column("remittance_reference", sa.String(100), nullable=True),
        sa.Column("refunded_at", sa.Date(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("refund_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0064_application_deposits: deposits exist. Remove them deliberately first.")
    op.drop_table(TABLE)
