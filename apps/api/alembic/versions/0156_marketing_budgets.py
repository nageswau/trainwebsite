"""mgmt-012 -- marketing budget & ROI: `marketing_budgets` (a month's budget per channel, entered by the partner or the accountant).

Revision ID: 0156_marketing_budgets
Revises: 0155_finance_balances

docs/superpowers/specs/2026-10-13-mgmt-012-marketing-roi-design.md §3 (DEC-SCOPE-206). One new table; nothing existing changes. 0001
builds a fresh database from the current models, which already carry the table, so the step is guarded. CHECKS repeats app.models
with a frozen copy of the 13 lead sources (test_mgmt_012_migration). downgrade() refuses while any row exists: it would drop budgets.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0156_marketing_budgets"
down_revision = "0155_finance_balances"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHANNELS = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral", "exhibition_event", "bdm", "other")
CHECKS = {  # must equal app.models.MARKETING_BUDGET_CHECKS
    "ck_marketing_budgets_month": "EXTRACT(DAY FROM month) = 1",
    "ck_marketing_budgets_amount": "amount >= 0",
    "ck_marketing_budgets_channel": f"channel IN ({', '.join(repr(s) for s in CHANNELS)})",
}


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "marketing_budgets" in existing:
        return
    op.create_table(
        "marketing_budgets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        _user("created_by_user_id"),
        _user("updated_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("month", "channel", name="uq_marketing_budgets_month_channel"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM marketing_budgets LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0156_marketing_budgets: marketing budgets exist. Remove them deliberately first.")
    op.drop_table("marketing_budgets")
