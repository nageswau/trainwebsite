"""mgmt-014 -- the investment register: `investment_code_seq` and `investments`.

Revision ID: 0151_investments
Revises: 0150_management_ledger

docs/superpowers/specs/2026-10-12-mgmt-014-investment-register-design.md §3 (DEC-SCOPE-190). One new table; no existing row changes. 0001
builds a fresh database from the current models, which already carry it, so each step is guarded. CHECKS repeats app.models
(test_mgmt_014_migration). downgrade() refuses while any investment exists: it would drop partner-only financial records.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0151_investments"
down_revision = "0150_management_ledger"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.INVESTMENT_CHECKS
    "ck_investments_status": "status IN ('planned', 'active', 'completed', 'cancelled')",
    "ck_investments_vertical": "vertical IN ('abroad', 'it', 'recruitment', 'school', 'shared', 'other')",
    "ck_investments_investor": "(investor_kind = 'company' AND investor_user_id IS NULL) OR (investor_kind = 'partner' AND investor_user_id IS NOT NULL)",
    "ck_investments_amount": "amount > 0",
    "ck_investments_returns": "(expected_return IS NULL OR expected_return >= 0) AND (actual_return IS NULL OR actual_return >= 0)",
}


def _user_fk(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS investment_code_seq")
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "investments" not in tables:
        op.create_table(
            "investments",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("invested_on", sa.Date(), nullable=False),
            sa.Column("investor_kind", sa.String(10), nullable=False),
            _user_fk("investor_user_id", nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("purpose", sa.String(200), nullable=False),
            sa.Column("vertical", sa.String(16), nullable=False),
            sa.Column("expected_return", sa.Numeric(12, 2), nullable=True),
            sa.Column("actual_return", sa.Numeric(12, 2), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("notes", sa.Text(), nullable=True),
            _user_fk("created_by_user_id"),
            _user_fk("updated_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("code", name="uq_investments_code"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("ix_investments_invested_on", "investments", ["invested_on"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM investments LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0151_investments: investments exist. Remove them deliberately first.")
    op.drop_table("investments")
    op.execute("DROP SEQUENCE IF EXISTS investment_code_seq")
