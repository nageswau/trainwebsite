"""Add EMISchedule/Invoice/Receipt/PaymentWebhookEvent + Payment columns (PAY-001/STU-010).

Revision ID: 0022_payment_billing_emi
Revises: 0021_country_interview_prep

DATA_MODEL.md #7.2 confirms Invoice/Receipt/EMISchedule/PaymentWebhookEvent as part of the
Payment domain (mislabeled "carries over" there -- none existed in code; corrected in the same
pass as this migration). Net-new. `Payment` gains `is_manual` (STU-010-AC02's alt path),
`emi_schedule_id`/`installment_no` (installment grouping), and checkout idempotency-replay
columns (API_CONTRACT.md #0.2).
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_payment_billing_emi"
down_revision = "0021_country_interview_prep"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "emi_schedules" not in tables:
        op.create_table(
            "emi_schedules",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("division", sa.String(30), nullable=False, index=True),
            sa.Column("reference_type", sa.String(50), nullable=False),
            sa.Column("reference_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
            sa.Column("installment_count", sa.Integer, nullable=False),
            sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    payment_columns = {c["name"] for c in inspector.get_columns("payments")}
    if "is_manual" not in payment_columns:
        op.add_column("payments", sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "emi_schedule_id" not in payment_columns:
        op.add_column("payments", sa.Column("emi_schedule_id", sa.Uuid(as_uuid=True), sa.ForeignKey("emi_schedules.id"), nullable=True))
        op.create_index("ix_payments_emi_schedule_id", "payments", ["emi_schedule_id"])
    if "installment_no" not in payment_columns:
        op.add_column("payments", sa.Column("installment_no", sa.Integer(), nullable=True))
    if "checkout_idempotency_key" not in payment_columns:
        op.add_column("payments", sa.Column("checkout_idempotency_key", sa.String(200), nullable=True))
    if "checkout_provider_order_id" not in payment_columns:
        op.add_column("payments", sa.Column("checkout_provider_order_id", sa.String(160), nullable=True))

    if "invoices" not in tables:
        op.create_table(
            "invoices",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("payment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False, unique=True, index=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("division", sa.String(30), nullable=False, index=True),
            sa.Column("invoice_no", sa.String(60), nullable=False, unique=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
            sa.Column("file_url", sa.String(500), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "receipts" not in tables:
        op.create_table(
            "receipts",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("payment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False, unique=True, index=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("division", sa.String(30), nullable=False, index=True),
            sa.Column("receipt_no", sa.String(60), nullable=False, unique=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
            sa.Column("file_url", sa.String(500), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "payment_webhook_events" not in tables:
        op.create_table(
            "payment_webhook_events",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(30), nullable=False),
            sa.Column("event_id", sa.String(160), nullable=False, unique=True),
            sa.Column("signature_verified", sa.Boolean(), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("payment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("payments.id"), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("payment_webhook_events")
    op.drop_table("receipts")
    op.drop_table("invoices")
    op.drop_column("payments", "checkout_provider_order_id")
    op.drop_column("payments", "checkout_idempotency_key")
    op.drop_column("payments", "installment_no")
    op.drop_index("ix_payments_emi_schedule_id", table_name="payments")
    op.drop_column("payments", "emi_schedule_id")
    op.drop_column("payments", "is_manual")
    op.drop_table("emi_schedules")
