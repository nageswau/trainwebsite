"""mgmt-013 -- accounts dashboard: `finance_balances` (month-end cash/bank, payables and tax liabilities, entered by hand).

Revision ID: 0155_finance_balances
Revises: 0154_salaries

docs/superpowers/specs/2026-10-12-mgmt-013-accounts-dashboard-design.md §3 (DEC-SCOPE-195). One new table; nothing existing changes. 0001
builds a fresh database from the current models, which already carry the table, so the step is guarded. CHECKS repeats app.models
(test_mgmt_013_migration). downgrade() refuses while any row exists: it would drop finance records.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0155_finance_balances"
down_revision = "0154_salaries"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.FINANCE_BALANCE_CHECKS
    "ck_finance_balances_month": "EXTRACT(DAY FROM month) = 1",
    "ck_finance_balances_payables": "payables >= 0",
    "ck_finance_balances_tax": "tax_liabilities >= 0",
}


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "finance_balances" in existing:
        return
    op.create_table(
        "finance_balances",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("month", sa.Date(), nullable=False),
        *(sa.Column(name, sa.Numeric(14, 2), nullable=True) for name in ("cash_bank", "payables", "tax_liabilities")),
        _user("created_by_user_id"),
        _user("updated_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("month", name="uq_finance_balances_month"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM finance_balances LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0155_finance_balances: finance balances exist. Remove them deliberately first.")
    op.drop_table("finance_balances")
