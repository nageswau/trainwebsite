"""mgmt-022 -- school money: `schools.contract_value` / `renewal_value` and the ledger's school tag `ledger_entries.school_id`.

Revision ID: 0162_school_values
Revises: 0161_management_meetings

docs/superpowers/specs/2026-10-14-mgmt-022-school-dashboard-design.md §4 (SD13, SD14). Three nullable columns; no existing row changes.
0001 builds a fresh database from the current models, which already carry them, so each step is guarded. VALUE_CHECKS / SCHOOL_CHECK
repeat app.models (test_mgmt_022_migration). downgrade() refuses while a value or a tag is set: it would drop financial data.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0162_school_values"
down_revision = "0161_management_meetings"
branch_labels = None
depends_on = None

VALUE_CHECKS = {  # must equal app.models.SCHOOL_VALUE_CHECKS
    "ck_schools_contract_value": "contract_value IS NULL OR contract_value >= 0",
    "ck_schools_renewal_value": "renewal_value IS NULL OR renewal_value >= 0",
}
SCHOOL_CHECK = "school_id IS NULL OR (kind = 'income' AND vertical = 'school')"  # must equal app.models.LEDGER_SCHOOL_CHECK
INDEX = "ix_ledger_entries_school_date"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    offline = op.get_context().as_sql  # offline SQL: emit everything
    schools = set() if offline else _columns("schools")
    for column in ("contract_value", "renewal_value"):
        if column not in schools:
            op.add_column("schools", sa.Column(column, sa.Numeric(14, 2), nullable=True))
            op.create_check_constraint(f"ck_schools_{column}", "schools", VALUE_CHECKS[f"ck_schools_{column}"])
    if offline or "school_id" not in _columns("ledger_entries"):
        op.add_column("ledger_entries", sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True))
        op.create_check_constraint("ck_ledger_entries_school", "ledger_entries", SCHOOL_CHECK)
        op.create_index(INDEX, "ledger_entries", ["school_id", "entry_date"], postgresql_where=sa.text("school_id IS NOT NULL"))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        tagged = bind.execute(sa.text("SELECT 1 FROM ledger_entries WHERE school_id IS NOT NULL LIMIT 1")).first()
        valued = bind.execute(sa.text("SELECT 1 FROM schools WHERE contract_value IS NOT NULL OR renewal_value IS NOT NULL LIMIT 1")).first()
        if tagged or valued:
            raise RuntimeError("Cannot downgrade 0162_school_values: school values or school-tagged ledger entries exist. Remove them deliberately first.")
    op.drop_index(INDEX, table_name="ledger_entries")
    op.drop_column("ledger_entries", "school_id")  # drops its FK and CHECK with it
    op.drop_column("schools", "renewal_value")
    op.drop_column("schools", "contract_value")
