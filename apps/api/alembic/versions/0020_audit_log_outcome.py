"""Add AuditLog.outcome (SEC-001).

Revision ID: 0020_audit_log_outcome
Revises: 0019_commission_payout_approval

DATA_MODEL.md #7.3 names `outcome` as a required AuditLog field ("actor_user_id, action,
resource_type, resource_id, outcome, metadata, created_at"); the existing model never had
it. NFR-AUDIT-001 / the SEC-001 catalog description confirm the same: "logged with actor,
timestamp, outcome." Existing/untouched call sites default to "recorded" (this feature's
confirmed scope is specifically AGT-001 approve/reject and AGT-004 payout-approval, per
SEC-001's own catalog description -- not a rewrite of every AuditLog call site in the
codebase); those two features' call sites are updated to set a real business-outcome value
("approved"/"rejected"/"pending"/"approved").
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_audit_log_outcome"
down_revision = "0019_commission_payout_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("audit_logs")}
    if "outcome" not in columns:
        op.add_column("audit_logs", sa.Column("outcome", sa.String(30), nullable=False, server_default="recorded"))


def downgrade() -> None:
    op.drop_column("audit_logs", "outcome")
