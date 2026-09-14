"""Add AgentCommission.created_by (AGT-003).

Revision ID: 0018_agent_commission_created_by
Revises: 0017_employer_registration

DATA_MODEL.md #6.7: distinguishes a commission the new automatic enrolled-stage trigger
created ("system_trigger") from the base codebase's existing manual-entry path
("admin_manual") -- needed so an Overseas Admin's "set/adjust amount" action (AGT-003-
AC02) and AGT-004's later two-gate payout-approval check can tell them apart. Existing
rows (all created via the base codebase's manual path) default to "admin_manual".
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_agent_commission_created_by"
down_revision = "0017_employer_registration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("agent_commissions")}
    if "created_by" not in columns:
        op.add_column("agent_commissions", sa.Column("created_by", sa.String(20), nullable=False, server_default="admin_manual"))


def downgrade() -> None:
    op.drop_column("agent_commissions", "created_by")
