"""dtu-001 -- Direct Tie-ups: catalogue logo / campuses / fee block, course texts, and the agent commission.

Revision ID: 0157_direct_tieups
Revises: 0156_marketing_budgets

docs/superpowers/specs/2026-10-13-dtu-001-direct-tieups-design.md §3 (DEC-SCOPE-209). All columns nullable (campuses defaults to []),
no backfill. 0001 builds a fresh database from the current models, so every step is guarded. CHECKS repeats
app.models.UNIVERSITY_AGENT_COMMISSION_CHECKS (test_dtu_001_migration). downgrade() refuses while any agent commission exists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0157_direct_tieups"
down_revision = "0156_marketing_budgets"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_universities_agent_commission_one": "agent_commission_percent IS NULL OR agent_commission_amount IS NULL",
    "ck_universities_agent_commission_percent": "agent_commission_percent IS NULL OR (agent_commission_percent > 0 AND agent_commission_percent <= 100)",
    "ck_universities_agent_commission_amount": "(agent_commission_amount IS NULL) = (agent_commission_currency IS NULL) AND (agent_commission_amount IS NULL OR agent_commission_amount > 0)",
    "ck_universities_agent_commission_currency": "agent_commission_currency IS NULL OR agent_commission_currency IN ('INR', 'USD', 'GBP', 'EUR', 'CAD', 'AUD', 'NZD', 'AED')",
}  # must equal app.models.UNIVERSITY_AGENT_COMMISSION_CHECKS
UNIVERSITY_COLUMNS = (
    ("logo_url", sa.String(500)),
    ("campuses", sa.JSON()),
    ("fee_structure", sa.Text()),
    ("agent_commission_percent", sa.Numeric(5, 2)),
    ("agent_commission_amount", sa.Numeric(12, 2)),
    ("agent_commission_currency", sa.String(3)),
    ("agent_commission_note", sa.String(300)),
)
COURSE_COLUMNS = (("campus", sa.String(200)), ("fee_text", sa.String(300)), ("intake_text", sa.String(200)))


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def _add(inspector, table: str, columns) -> None:
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns(table)}
    for name, type_ in columns:
        if name not in present:
            default = sa.text("'[]'") if name == "campuses" else None
            op.add_column(table, sa.Column(name, type_, nullable=True, server_default=default))


def upgrade() -> None:
    inspector = _inspector()
    _add(inspector, "universities", UNIVERSITY_COLUMNS)
    _add(inspector, "overseas_courses", COURSE_COLUMNS)
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("universities")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "universities", sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text(
            "SELECT 1 FROM universities WHERE agent_commission_percent IS NOT NULL OR agent_commission_amount IS NOT NULL LIMIT 1"
        )).first()
        if found:
            raise RuntimeError("Cannot downgrade 0157_direct_tieups: agent commissions exist. Remove them deliberately first.")
    for name in reversed(CHECKS):
        op.drop_constraint(name, "universities", type_="check")
    for name, _ in reversed(COURSE_COLUMNS):
        op.drop_column("overseas_courses", name)
    for name, _ in reversed(UNIVERSITY_COLUMNS):
        op.drop_column("universities", name)
