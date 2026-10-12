"""mgmt-011 -- salary management: `departments` (+ seed) and `salary_month_totals`; the manual "Salaries" ledger category is deactivated.

Revision ID: 0153_salaries
Revises: 0152_management_discussions

docs/superpowers/specs/2026-10-12-mgmt-011-salary-management-design.md §3 (DEC-SCOPE-193). New tables, plus one existing row changed: the
mgmt-004 "Salaries" expense category is deactivated (SM9), because saved salary totals now reach the ledger as automatic lines and must
not be entered twice; its entries keep it (ML3). 0001 builds a fresh database from the current models, which already carry the tables,
so each step is guarded and the departments are seeded whenever the table is empty. CHECKS repeats app.models (test_mgmt_011_migration).
downgrade() refuses while any salary row exists: it would drop finance records.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0153_salaries"
down_revision = "0152_management_discussions"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
SEED = (  # SM1 (Q-13 interim)
    "Management", "Counseling", "Telecalling", "Business Development", "Training", "Placement & Recruitment", "Partnerships", "Marketing",
    "Accounts & Administration", "Operations & Support",
)  # fmt: skip
MONEY = ("payable", "paid", "incentives", "commissions", "employer_cost")
CHECKS = {  # must equal app.models.SALARY_CHECKS
    "ck_salary_month_totals_month": "EXTRACT(DAY FROM month) = 1",
    "ck_salary_month_totals_headcount": "headcount >= 0",
    "ck_salary_month_totals_money": " AND ".join(f"{c} >= 0" for c in MONEY),
}
SALARIES_CATEGORY = "UPDATE ledger_categories SET active = {active} WHERE kind = 'expense' AND name = 'Salaries'"


def _user(name: str, nullable: bool) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "departments" not in existing:
        op.create_table(
            "departments",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            _user("created_by_user_id", True),
            _user("updated_by_user_id", True),
            *_timestamps(),
        )
        op.create_index("uq_departments_name", "departments", [sa.text("lower(name)")], unique=True)
    if "salary_month_totals" not in existing:
        op.create_table(
            "salary_month_totals",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("department_id", UUID, sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("headcount", sa.Integer(), nullable=False),
            *(sa.Column(name, sa.Numeric(14, 2), nullable=False) for name in MONEY),
            _user("created_by_user_id", False),
            _user("updated_by_user_id", False),
            *_timestamps(),
            sa.UniqueConstraint("month", "department_id", name="uq_salary_month_totals_month_department"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("ix_salary_month_totals_month", "salary_month_totals", ["month"])
    if op.get_context().as_sql or not op.get_bind().execute(sa.text("SELECT 1 FROM departments LIMIT 1")).first():
        table = sa.table("departments", sa.column("id", UUID), sa.column("name", sa.String))  # typed, so --sql can render the literals
        op.bulk_insert(table, [{"id": uuid.uuid4(), "name": name} for name in SEED])
    op.execute(SALARIES_CATEGORY.format(active="false"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM salary_month_totals LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0153_salaries: salary rows exist. Remove them deliberately first.")
    op.execute(SALARIES_CATEGORY.format(active="true"))
    op.drop_table("salary_month_totals")
    op.drop_table("departments")
