"""pob-012 -- vendor payables and receivables (DEC-SCOPE-433 W2, W3, W10).

Revision ID: 0314_vendor_bills
Revises: 0313_submissions

docs/superpowers/specs/2026-11-08-pob-012-vendor-commercials-performance-design.md. Additive only: `vendor_bills` and
`vendor_bill_payments`. 0001 runs `create_all` from today's models, so a fresh database already has both tables: each is created only when
missing. BILL_CHECKS and PAYMENT_CHECKS are frozen copies of `models.VENDOR_BILL_CHECKS` and `models.VENDOR_BILL_PAYMENT_CHECKS`. The
downgrade drops both tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0314_vendor_bills"
down_revision = "0313_submissions"
branch_labels = None
depends_on = None

BILL_CHECKS = {
    "ck_vendor_bills_kind": "kind IN ('payable', 'receivable')",
    "ck_vendor_bills_amount": "amount > 0",
    "ck_vendor_bills_due": "due_date >= bill_date",
    "ck_vendor_bills_cancel": "(cancelled_at IS NULL) = (cancelled_by_user_id IS NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
}
PAYMENT_CHECKS = {"ck_vendor_bill_payments_amount": "amount > 0"}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "vendor_bills" not in tables:
        op.create_table(
            "vendor_bills",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("bill_number", sa.String(40), nullable=False),
            sa.Column("bill_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("milestone", sa.String(120), nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("cancel_reason", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in BILL_CHECKS.items()),
        )
        op.create_index("uq_vendor_bills_number", "vendor_bills", ["company_id", sa.text("lower(bill_number)")], unique=True)
        op.create_index("ix_vendor_bills_company", "vendor_bills", ["company_id", "bill_date"])
    if "vendor_bill_payments" not in tables:
        op.create_table(
            "vendor_bill_payments",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("bill_id", sa.Uuid(), sa.ForeignKey("vendor_bills.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("paid_on", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in PAYMENT_CHECKS.items()),
        )
        op.create_index("ix_vendor_bill_payments_bill", "vendor_bill_payments", ["bill_id", "paid_on"])


def downgrade() -> None:
    op.drop_table("vendor_bill_payments")
    op.drop_table("vendor_bills")
