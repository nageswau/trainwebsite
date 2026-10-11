"""rec-031 -- recruiter revenue: the per-requirement fee override on jobs, recruiter_invoices and recruiter_payments.

Revision ID: 0146_recruiter_revenue
Revises: 0145_university_onboarding

docs/superpowers/specs/2026-10-11-rec-031-recruiter-revenue-design.md §2 (DEC-SCOPE-175). Two nullable columns on jobs and two new tables;
no existing row changes, so there is no backfill. 0001 builds a fresh database from the current models, which already carry them, so each
piece is created only when missing (0117's idiom). The CHECK strings repeat app.models (test_rec_031_migration). downgrade() refuses while
any invoice or fee override exists: it would drop recorded commercial data.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0146_recruiter_revenue"
down_revision = "0145_university_onboarding"
branch_labels = None
depends_on = None

INVOICES = "recruiter_invoices"
PAYMENTS = "recruiter_payments"
UUID = postgresql.UUID(as_uuid=True)
JOB_CHECKS = {
    "ck_jobs_fee_pair": "(fee_basis IS NULL) = (fee_value IS NULL)",
    "ck_jobs_fee_basis": "fee_basis IS NULL OR fee_basis IN ('fixed', 'percent_of_ctc')",
    "ck_jobs_fee_value": "fee_value IS NULL OR (fee_value >= 0 AND (fee_basis <> 'percent_of_ctc' OR fee_value <= 100))",
}
INVOICE_CHECKS = {
    "ck_recruiter_invoices_amount": "amount > 0",
    "ck_recruiter_invoices_due": "due_date >= invoice_date",
    "ck_recruiter_invoices_cancel": "(cancelled_at IS NULL) = (cancelled_by_user_id IS NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
}
PAYMENT_CHECKS = {"ck_recruiter_payments_amount": "amount > 0"}


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    tables = set(inspector.get_table_names()) if inspector else set()
    job_columns = {c["name"] for c in inspector.get_columns("jobs")} if inspector else set()
    job_checks = {c["name"] for c in inspector.get_check_constraints("jobs")} if inspector else set()
    if "fee_basis" not in job_columns:
        op.add_column("jobs", sa.Column("fee_basis", sa.String(20), nullable=True))
    if "fee_value" not in job_columns:
        op.add_column("jobs", sa.Column("fee_value", sa.Numeric(12, 2), nullable=True))
    for name, sql in JOB_CHECKS.items():
        if name not in job_checks:
            op.create_check_constraint(name, "jobs", sql)
    if INVOICES not in tables:
        op.create_table(
            INVOICES,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("invoice_number", sa.String(40), nullable=False),
            sa.Column("invoice_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("cancel_reason", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in INVOICE_CHECKS.items()),
        )
        op.create_index("uq_recruiter_invoices_number", INVOICES, [sa.text("lower(invoice_number)")], unique=True)
        op.create_index("ix_recruiter_invoices_job", INVOICES, ["job_id", "invoice_date"])
    if PAYMENTS not in tables:
        op.create_table(
            PAYMENTS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("invoice_id", UUID, sa.ForeignKey("recruiter_invoices.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("received_on", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in PAYMENT_CHECKS.items()),
        )
        op.create_index("ix_recruiter_payments_invoice", PAYMENTS, ["invoice_id", "received_on"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {INVOICES} LIMIT 1")).first() or bind.execute(sa.text("SELECT 1 FROM jobs WHERE fee_basis IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0146_recruiter_revenue: revenue data exists (invoices or fee overrides). Clear it deliberately first.")
    op.drop_table(PAYMENTS)
    op.drop_table(INVOICES)
    for name in JOB_CHECKS:
        op.drop_constraint(name, "jobs", type_="check")
    op.drop_column("jobs", "fee_value")
    op.drop_column("jobs", "fee_basis")
