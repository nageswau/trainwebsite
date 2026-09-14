"""Add schools, school_account_invites (SCH-003).

Revision ID: 0023_school_onboarding
Revises: 0022_payment_billing_emi

`DATA_MODEL.md` §6.11/§6.15. Net-new -- no equivalent exists in the base codebase.
`School` (partner record, minimal confirmed-scope fields) and `SchoolAccountInvite`
(Coordinator-issued invite for Principal/Teacher/Parent accounts, single-use,
institution-scoped, `DEC-SCOPE-012`/`SCH-003-AC06`).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023_school_onboarding"
down_revision = "0022_payment_billing_emi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "schools" not in existing:
        op.create_table(
            "schools",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("city", sa.String(120), nullable=True),
            sa.Column("state", sa.String(120), nullable=True),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "school_account_invites" not in existing:
        op.create_table(
            "school_account_invites",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("role", sa.String(50), nullable=False),
            sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(128), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(160), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_account_invites_school_id", "school_account_invites", ["school_id"])
        op.create_index("ix_school_account_invites_token_hash", "school_account_invites", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_school_account_invites_token_hash", table_name="school_account_invites")
    op.drop_index("ix_school_account_invites_school_id", table_name="school_account_invites")
    op.drop_table("school_account_invites")
    op.drop_table("schools")
