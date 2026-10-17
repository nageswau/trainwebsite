"""AGN-024 -- agent signup KYC documents: agent_org_kyc_documents + agent_orgs.kyc_required.

Revision ID: 0164_agent_org_kyc
Revises: 0163_monthly_reviews

docs/superpowers/specs/2026-10-17-agent-signup-kyc-design.md (DEC-SCOPE-224). Every existing agent_orgs row gets kyc_required=false
(K4: existing agencies approve unchanged). 0001 builds a fresh database from the current models, which already carry both, so each
is created only when missing (0160's idiom). downgrade() refuses while KYC rows exist: identity documents are not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0164_agent_org_kyc"
down_revision = "0163_monthly_reviews"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.KYC_CHECKS
    "ck_agent_org_kyc_documents_type": "doc_type IN ('pan', 'aadhaar', 'business_license')",
    "ck_agent_org_kyc_documents_status": "status IN ('pending', 'verified', 'rejected')",
    "ck_agent_org_kyc_documents_reason": "(status = 'rejected') = (rejection_reason IS NOT NULL)",
}


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or "kyc_required" not in {c["name"] for c in inspector.get_columns("agent_orgs")}:
        op.add_column("agent_orgs", sa.Column("kyc_required", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    if not offline and "agent_org_kyc_documents" in inspector.get_table_names():
        return
    op.create_table(
        "agent_org_kyc_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("agent_orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("doc_number", sa.String(64), nullable=False),
        sa.Column("file_key", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "doc_type", name="uq_agent_org_kyc_documents_org_type"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_agent_org_kyc_documents_org_id", "agent_org_kyc_documents", ["org_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM agent_org_kyc_documents LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0164_agent_org_kyc: KYC documents exist. Export them deliberately first.")
    op.drop_index("ix_agent_org_kyc_documents_org_id", table_name="agent_org_kyc_documents")
    op.drop_table("agent_org_kyc_documents")
    op.drop_column("agent_orgs", "kyc_required")
