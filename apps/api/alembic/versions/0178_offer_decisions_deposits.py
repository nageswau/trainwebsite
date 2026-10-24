"""ccrm-025 -- the student's decision on an offer (application_offers.decision / decision_date / decided_by_id) and the counselor's
manual deposit record (application_deposit_records).

Revision ID: 0178_offer_decisions_deposits
Revises: 0177_visa_lifecycle

docs/superpowers/specs/2026-10-24-ccrm-025-offer-decisions-deposits-design.md (DEC-SCOPE-255). Existing offers become `considering`
(the server default); nothing else is backfilled. 0001 builds a fresh database from the current models, which already carry both, so each
step runs only when missing (0166's idiom). DECISIONS / DEPOSIT_STATUSES repeat app.models (test_ccrm_025_migration). The downgrade
drops the table and the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0178_offer_decisions_deposits"
down_revision = "0177_visa_lifecycle"
branch_labels = None
depends_on = None

OFFERS = "application_offers"
DEPOSITS = "application_deposit_records"
DECISIONS = ("considering", "accepted", "declined", "expired")
DEPOSIT_STATUSES = ("not_required", "pending", "paid_to_university", "paid_via_edusphere")
OFFER_CHECKS = {
    "ck_application_offers_decision": f"decision IN {'(' + ', '.join(repr(v) for v in DECISIONS) + ')'}",
    "ck_application_offers_decision_dated": "(decision = 'considering') = (decision_date IS NULL)",
}
DEPOSIT_CHECKS = {
    "ck_application_deposit_records_status": f"payment_status IN {'(' + ', '.join(repr(v) for v in DEPOSIT_STATUSES) + ')'}",
    "ck_application_deposit_records_required": "(payment_status = 'not_required') = (NOT required)",
    "ck_application_deposit_records_amount": (
        "(required AND amount > 0 AND currency IS NOT NULL) OR (NOT required AND amount IS NULL AND currency IS NULL AND due_date IS NULL "
        "AND receipt_document_id IS NULL)"
    ),
    "ck_application_deposit_records_paid": "(paid_on IS NOT NULL) = (payment_status IN ('paid_to_university', 'paid_via_edusphere'))",
}


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspect()
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns(OFFERS)}
    if "decision" not in columns:
        op.add_column(OFFERS, sa.Column("decision", sa.String(20), nullable=False, server_default=sa.text("'considering'")))
        op.add_column(OFFERS, sa.Column("decision_date", sa.Date(), nullable=True))
        op.add_column(OFFERS, sa.Column("decided_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True))
        for name, sql in OFFER_CHECKS.items():
            op.create_check_constraint(name, OFFERS, sql)
    if inspector is not None and DEPOSITS in inspector.get_table_names():
        return
    op.create_table(
        DEPOSITS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("payment_status", sa.String(30), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("receipt_document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in DEPOSIT_CHECKS.items()),
    )


def downgrade() -> None:
    op.drop_table(DEPOSITS)
    for name in OFFER_CHECKS:
        op.drop_constraint(name, OFFERS, type_="check")
    for name in ("decided_by_id", "decision_date", "decision"):
        op.drop_column(OFFERS, name)
