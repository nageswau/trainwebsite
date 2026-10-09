"""upc-016 -- university_commission_terms: §15 commercial / commission terms (restricted, U2).

Revision ID: 0128_university_commission_terms
Revises: 0127_university_agreements

docs/superpowers/specs/2026-10-09-upc-016-commission-terms-design.md §2 (DEC-SCOPE-143). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry the table, so it is created only when missing (0117's idiom).
TRIGGERS / CURRENCIES / CHECKS repeat app.models (test_upc_016_migration). downgrade() refuses while any term exists: entered data is never
dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0128_university_commission_terms"
down_revision = "0127_university_agreements"
branch_labels = None
depends_on = None

TERMS = "university_commission_terms"
UUID = postgresql.UUID(as_uuid=True)
TRIGGERS = ("enrolment", "visa_and_enrolment", "tuition_paid")
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.COMMISSION_TERM_CHECKS
    "ck_university_commission_terms_one_rate": "(commission_percent IS NULL) <> (fixed_amount IS NULL)",
    "ck_university_commission_terms_percent": "commission_percent IS NULL OR (commission_percent > 0 AND commission_percent <= 100)",
    "ck_university_commission_terms_fixed": "fixed_amount IS NULL OR fixed_amount > 0",
    "ck_university_commission_terms_currency": _in("currency", CURRENCIES),
    "ck_university_commission_terms_trigger": _in("trigger", TRIGGERS),
}


def fk(target: str):
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    if not op.get_context().as_sql and TERMS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TERMS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("agreement_id", UUID, fk("university_agreements.id"), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("course_ids", sa.JSON(), nullable=False),
        sa.Column("country_ids", sa.JSON(), nullable=False),
        sa.Column("payment_timeline", sa.String(500), nullable=True),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("updated_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_university_commission_terms_agreement", TERMS, ["agreement_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TERMS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0128_university_commission_terms: commission terms exist. Remove them deliberately first.")
    op.drop_table(TERMS)
