"""AGN-012 -- visa_cases.visa_application_date, interview_date, decision, decided_at.

Revision ID: 0061_agent_visa_details
Revises: 0060_agent_app_enrollment

docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §3 (DEC-SCOPE-055). Four nullable columns and a CHECK on the decision;
no existing row is read or written. 0001 builds a fresh database from the current models, which already carry these columns and the
constraint, so every add is guarded (0057's and 0041's idioms). downgrade() refuses while visa details exist rather than silently
dropping them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0061_agent_visa_details"
down_revision = "0060_agent_app_enrollment"
branch_labels = None
depends_on = None

TABLE = "visa_cases"
COLUMNS = (("visa_application_date", sa.Date()), ("interview_date", sa.Date()), ("decision", sa.String(20)), ("decided_at", sa.DateTime(timezone=True)))
DECISION_CHECK = "decision IN ('approved', 'refused', 'withdrawn')"
CHECK_NAME = "ck_visa_cases_decision"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    if CHECK_NAME not in checks:
        op.create_check_constraint(CHECK_NAME, TABLE, DECISION_CHECK)


def downgrade() -> None:
    if not op.get_context().as_sql:
        recorded = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {recorded}")).scalar():
            raise RuntimeError("Refusing to downgrade 0061_agent_visa_details: visa details exist")
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
