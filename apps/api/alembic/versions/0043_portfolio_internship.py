"""ENH-021 -- internship tracking on the portfolio `internship` section.

Revision ID: 0043_portfolio_internship
Revises: 0042_career_record_fields

docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §4.2 (DEC-SCOPE-032).
Additive only: nullable columns and three CHECKs (attendance range, completion values, internship-only fields).
No backfill. `downgrade()` drops what this adds; certificate objects already in storage become orphans and must be
removed by hand (prefix `portfolio-certificates/`).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043_portfolio_internship"
down_revision = "0042_career_record_fields"
branch_labels = None
depends_on = None

TABLE = "portfolio_entries"
COLUMNS = (
    ("mentor_name", sa.String(200)), ("mentor_designation", sa.String(200)), ("attendance_percent", sa.Integer()),
    ("completion_status", sa.String(20)), ("feedback", sa.Text()), ("skills_acquired", postgresql.JSON(none_as_null=True)),
    ("certificate_key", sa.String(300)), ("certificate_content_type", sa.String(50)),
)
CHECKS = {
    "ck_portfolio_attendance_percent": "attendance_percent IS NULL OR attendance_percent BETWEEN 0 AND 100",
    "ck_portfolio_completion_status": "completion_status IS NULL OR completion_status IN ('not_started', 'in_progress', 'completed', 'discontinued')",
    "ck_portfolio_internship_fields": "section = 'internship' OR (" + " AND ".join(f"{name} IS NULL" for name, _ in COLUMNS) + ")",
}


def upgrade() -> None:
    # Guarded like 0041/0042: 0001_initial builds tables from the current models on a from-scratch replay.
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    for name, condition in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, condition)


def downgrade() -> None:
    for name in reversed(CHECKS):
        op.drop_constraint(name, TABLE, type_="check")
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name)
