"""ccrm-049 -- payment receipt / proof: `payments.proof_document_id` -> `student_documents.id` (ON DELETE SET NULL, nullable).

Revision ID: 0216_payment_proof_documents
Revises: 0215_payment_discount_ledger

docs/superpowers/specs/2026-10-28-ccrm-049-payment-proof-upload-design.md (DEC-SCOPE-324). 0001 builds a fresh database from the current
models, which already carry the column, so it is added only when missing. No backfill: no payment had a proof before. The downgrade
drops the column (and with it the foreign key).
"""

import sqlalchemy as sa

from alembic import op

revision = "0216_payment_proof_documents"
down_revision = "0215_payment_discount_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "proof_document_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("payments")}:
        op.add_column("payments", sa.Column("proof_document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "proof_document_id")
