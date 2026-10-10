"""upc-019 -- university_commission_receipts: commission received from a university (restricted, U2).

Revision ID: 0144_commission_receipts
Revises: 0143_university_probability

docs/superpowers/specs/2026-10-10-upc-019-commission-ledger-design.md §2 (DEC-SCOPE-163). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry the table, so it is created only when missing (0117's idiom).
CURRENCIES / CHECKS repeat app.models (test_upc_019_migration). downgrade() refuses while any receipt exists: money records are never
dropped silently.

Re-chained on 2026-10-10: drafted as `0143_commission_receipts` on `0142_profile_shares`; upc-023 (`0143_university_probability`) merged
first. A database stamped at the draft is re-stamped with `alembic stamp --purge 0142_profile_shares`, then `upgrade head` (the table step
is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0144_commission_receipts"
down_revision = "0143_university_probability"
branch_labels = None
depends_on = None

RECEIPTS = "university_commission_receipts"
UUID = postgresql.UUID(as_uuid=True)
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.COMMISSION_RECEIPT_CHECKS
    "ck_university_commission_receipts_amount": "amount > 0",
    "ck_university_commission_receipts_currency": _in("currency", CURRENCIES),
    "ck_university_commission_receipts_note": "note IS NULL OR char_length(note) <= 500",
}


def fk(target: str):
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    if not op.get_context().as_sql and RECEIPTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        RECEIPTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("application_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_university_commission_receipts_university", RECEIPTS, ["university_id", "received_on"])
    op.create_index("uq_university_commission_receipts_reference", RECEIPTS, ["university_id", sa.text("lower(reference)")], unique=True)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {RECEIPTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0144_commission_receipts: commission receipts exist. Remove them deliberately first.")
    op.drop_table(RECEIPTS)
