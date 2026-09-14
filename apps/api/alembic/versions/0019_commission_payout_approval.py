"""Add AgentCommission payout-approval columns (AGT-004).

Revision ID: 0019_commission_payout_approval
Revises: 0018_agent_commission_created_by

DATA_MODEL.md #6.7: `payout_approved_by_user_id` / `payout_approved_at` are net-new --
"closes the gap REFERENCE_IMPLEMENTATION_FINDINGS.md #5.4/#9 identified" -- the base
codebase has no payout-approval concept at all. Needed so `status` can never reach `paid`
without recording which Overseas Admin identity approved it, distinct from whoever
created/adjusted the commission where that separation is enforceable (NFR-SEC-002).
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_commission_payout_approval"
down_revision = "0018_agent_commission_created_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("agent_commissions")}
    if "payout_approved_by_user_id" not in columns:
        op.add_column("agent_commissions", sa.Column("payout_approved_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    if "payout_approved_at" not in columns:
        op.add_column("agent_commissions", sa.Column("payout_approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_commissions", "payout_approved_at")
    op.drop_column("agent_commissions", "payout_approved_by_user_id")
