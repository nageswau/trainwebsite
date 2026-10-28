"""ccrm-051 -- the agent-Master commission per course: `overseas_courses.agent_commission_percent / _amount / _currency / _note`.

Revision ID: 0217_course_agent_commission
Revises: 0216_payment_proof_documents

docs/superpowers/specs/2026-10-28-ccrm-051-course-agent-commission-design.md (DEC-SCOPE-327). All columns nullable (NULL = the
university's value applies), no backfill. 0001 builds a fresh database from the current models, so every step is guarded. CHECKS repeats
app.models.COURSE_AGENT_COMMISSION_CHECKS (test_ccrm_051_migration). downgrade() refuses while any course agent commission exists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0217_course_agent_commission"
down_revision = "0216_payment_proof_documents"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_overseas_courses_agent_commission_one": "agent_commission_percent IS NULL OR agent_commission_amount IS NULL",
    "ck_overseas_courses_agent_commission_percent": "agent_commission_percent IS NULL OR (agent_commission_percent > 0 AND agent_commission_percent <= 100)",
    "ck_overseas_courses_agent_commission_amount": "(agent_commission_amount IS NULL) = (agent_commission_currency IS NULL) AND (agent_commission_amount IS NULL OR agent_commission_amount > 0)",
    "ck_overseas_courses_agent_commission_currency": "agent_commission_currency IS NULL OR agent_commission_currency IN ('INR', 'USD', 'GBP', 'EUR', 'CAD', 'AUD', 'NZD', 'AED')",
}  # must equal app.models.COURSE_AGENT_COMMISSION_CHECKS
COLUMNS = (
    ("agent_commission_percent", sa.Numeric(5, 2)),
    ("agent_commission_amount", sa.Numeric(12, 2)),
    ("agent_commission_currency", sa.String(3)),
    ("agent_commission_note", sa.String(300)),
)


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns("overseas_courses")}
    for name, type_ in COLUMNS:
        if name not in present:
            op.add_column("overseas_courses", sa.Column(name, type_, nullable=True))
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("overseas_courses")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "overseas_courses", sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text(
            "SELECT 1 FROM overseas_courses WHERE agent_commission_percent IS NOT NULL OR agent_commission_amount IS NOT NULL LIMIT 1"
        )).first()
        if found:
            raise RuntimeError("Cannot downgrade 0217_course_agent_commission: course agent commissions exist. Remove them deliberately first.")
    for name in reversed(CHECKS):
        op.drop_constraint(name, "overseas_courses", type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column("overseas_courses", name)
