"""hrc-011 -- candidate compensation: currency, pay period and normalised annual INR per amount, a minimum, negotiability, and the
manual exchange-rate table.

Revision ID: 0251_candidate_compensation
Revises: 0250_compensation_grant

docs/superpowers/specs/2026-11-04-hrc-011-candidate-compensation-design.md (DEC-SCOPE-375). Nullable columns and one new table; 0001 builds
a fresh database from the current models, which already carry them, so each step runs only when missing (0222's idiom). Backfill (C9):
an existing amount was rupees a year, so it gets 'INR', 'year' and annual INR = the amount; nothing else changes. CHECKS is a frozen copy
of the model's strings at this revision. The downgrade drops the new columns, index, checks and table; the original amounts are untouched.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0251_candidate_compensation"
down_revision = "0250_compensation_grant"
branch_labels = None
depends_on = None

AMOUNTS = ("current", "expected", "minimum")
CHECKS = {
    "ck_candidates_minimum_salary": "minimum_salary IS NULL OR minimum_salary >= 0",
    "ck_candidates_salary_periods": "coalesce(current_salary_period, 'year') IN ('year', 'month') AND coalesce(expected_salary_period, 'year') IN ('year', 'month') AND coalesce(minimum_salary_period, 'year') IN ('year', 'month')",
}
INDEX = "ix_candidates_expected_annual_inr"


def _columns() -> list[sa.Column]:
    out = [sa.Column("minimum_salary", sa.Numeric(12, 2), nullable=True)]
    for amount in AMOUNTS:
        out += [
            sa.Column(f"{amount}_salary_currency", sa.String(3), nullable=True),
            sa.Column(f"{amount}_salary_period", sa.String(5), nullable=True),
            sa.Column(f"{amount}_annual_inr", sa.Numeric(18, 2), nullable=True),
        ]
    return [*out, sa.Column("salary_negotiable", sa.Boolean(), nullable=True)]


def upgrade() -> None:
    offline = op.get_context().as_sql
    bind = None if offline else op.get_bind()
    inspector = None if offline else sa.inspect(bind)
    existing = set() if offline else {c["name"] for c in inspector.get_columns("candidates")}
    for column in _columns():
        if column.name not in existing:
            op.add_column("candidates", column)
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("candidates")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "candidates", sql)
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes("candidates")}:
        op.create_index(INDEX, "candidates", ["expected_annual_inr"])
    if offline or "rec_fx_rates" not in set(inspector.get_table_names()):
        op.create_table(
            "rec_fx_rates",
            sa.Column("currency", sa.String(3), primary_key=True),
            sa.Column("inr_per_unit", sa.Numeric(12, 4), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.CheckConstraint("inr_per_unit > 0 AND inr_per_unit <= 10000", name="ck_rec_fx_rates_rate"),
        )
    for amount in ("current", "expected"):  # minimum is new: nothing to backfill
        op.execute(
            f"UPDATE candidates SET {amount}_salary_currency = 'INR', {amount}_salary_period = 'year', {amount}_annual_inr = {amount}_salary "
            f"WHERE {amount}_salary IS NOT NULL AND {amount}_salary_currency IS NULL"
        )


def downgrade() -> None:
    op.drop_table("rec_fx_rates")
    op.drop_index(INDEX, table_name="candidates")
    for name in CHECKS:
        op.drop_constraint(name, "candidates", type_="check")
    for column in _columns():
        op.drop_column("candidates", column.name)
