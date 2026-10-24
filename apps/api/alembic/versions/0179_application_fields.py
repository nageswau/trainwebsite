"""ccrm-013 -- application fields: faculty, campus, start date, portal link, university contact, tuition + currency, scholarship,
documents-complete and decision-due dates on overseas_applications, with their CHECKs.

Revision ID: 0179_application_fields
Revises: 0177_visa_lifecycle

docs/superpowers/specs/2026-10-24-ccrm-013-application-fields-design.md (DEC-SCOPE-256). Additive and nullable: no backfill, existing
rows keep every value. 0001 builds a fresh database from the current models, which already carry the columns, so each step runs only
when missing (0166's idiom). CURRENCIES / SCHOLARSHIP_STATUSES repeat app.application_fields (test_ccrm_013_migration). The downgrade
drops the CHECKs and the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0179_application_fields"
down_revision = "0177_visa_lifecycle"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
CURRENCIES = ("INR", "GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD", "AED")
SCHOLARSHIP_STATUSES = ("none", "applied", "awarded", "declined")
COLUMNS = (
    ("faculty", sa.String(140)),
    ("campus", sa.String(140)),
    ("course_start_date", sa.Date()),
    ("university_portal_url", sa.String(500)),
    ("university_contact_name", sa.String(140)),
    ("university_contact_email", sa.String(254)),
    ("tuition_fee", sa.Numeric(12, 2)),
    ("currency", sa.String(3)),
    ("scholarship_status", sa.String(20)),
    ("scholarship_amount", sa.Numeric(12, 2)),
    ("documents_completed_on", sa.Date()),
    ("decision_due_on", sa.Date()),
)


def _in(column: str, values) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_overseas_applications_currency": _in("currency", CURRENCIES),
    "ck_overseas_applications_scholarship_status": _in("scholarship_status", SCHOLARSHIP_STATUSES),
    "ck_overseas_applications_money": "(tuition_fee IS NULL OR tuition_fee >= 0) AND (scholarship_amount IS NULL OR scholarship_amount >= 0)",
    "ck_overseas_applications_scholarship_awarded": "scholarship_amount IS NULL OR scholarship_status = 'awarded'",
}


def _existing() -> tuple[set[str], set[str]]:
    if op.get_context().as_sql:
        return set(), set()
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(TABLE)}, {c["name"] for c in inspector.get_check_constraints(TABLE)}


def upgrade() -> None:
    columns, checks = _existing()
    for name, type_ in COLUMNS:
        if name not in columns:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)


def downgrade() -> None:
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name, _ in COLUMNS:
        op.drop_column(TABLE, name)
