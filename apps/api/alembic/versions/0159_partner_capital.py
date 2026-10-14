"""mgmt-015 -- partner capital accounts: `partner_capital_entries` and `partner_shares`.

Revision ID: 0159_partner_capital
Revises: 0158_social_proof

docs/superpowers/specs/2026-10-14-mgmt-015-partner-capital-accounts-design.md §3. Two new tables; no existing row changes. 0001 builds a
fresh database from the current models, which already carry them, so each step is guarded. ENTRY_CHECKS / SHARE_CHECKS repeat
app.models (test_mgmt_015_migration). downgrade() refuses while either table has rows: it would drop partner-only financial records.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0159_partner_capital"
down_revision = "0158_social_proof"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
ENTRY_CHECKS = {  # must equal app.models.CAPITAL_ENTRY_CHECKS
    "ck_partner_capital_entries_kind": "kind IN ('initial', 'additional', 'withdrawal', 'profit_distribution')",
    "ck_partner_capital_entries_amount": "amount > 0",
}
SHARE_CHECKS = {  # must equal app.models.PARTNER_SHARE_CHECKS
    "ck_partner_shares_month": "EXTRACT(DAY FROM effective_from) = 1",
    "ck_partner_shares_share_pct": "share_pct >= 0 AND share_pct <= 100",
    "ck_partner_shares_commitment": "commitment IS NULL OR commitment >= 0",
}
TABLES = ("partner_capital_entries", "partner_shares")


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "partner_capital_entries" not in tables:
        op.create_table(
            "partner_capital_entries",
            sa.Column("id", UUID, primary_key=True),
            _user_fk("partner_user_id"),
            sa.Column("entry_date", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            _user_fk("created_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ENTRY_CHECKS.items()),
        )
        op.create_index("ix_partner_capital_entries_partner_date", "partner_capital_entries", ["partner_user_id", "entry_date"])
    if "partner_shares" not in tables:
        op.create_table(
            "partner_shares",
            sa.Column("id", UUID, primary_key=True),
            _user_fk("partner_user_id"),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("share_pct", sa.Numeric(5, 2), nullable=False),
            sa.Column("commitment", sa.Numeric(12, 2), nullable=True),
            _user_fk("created_by_user_id"),
            _user_fk("updated_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("partner_user_id", "effective_from", name="uq_partner_shares_partner_month"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in SHARE_CHECKS.items()),
        )


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in TABLES):  # noqa: S608 -- fixed names
            raise RuntimeError("Cannot downgrade 0159_partner_capital: capital records exist. Remove them deliberately first.")
    for table in reversed(TABLES):
        op.drop_table(table)
