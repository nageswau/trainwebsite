"""ccrm-005 -- the spec §3 lead fields: contact preference, enquiry date, marketing consent and referral on `enquiries`; the overseas study
and academic answers on `lead_qualifications`; the lead's English tests (`lead_english_tests`).

Revision ID: 0182_lead_data_fields
Revises: 0181_lead_meetings

docs/superpowers/specs/2026-10-25-ccrm-005-lead-data-fields-design.md (DEC-SCOPE-260). Additive. `enquiry_date` is added nullable,
back-filled with each lead's created date in IST (LF4) and then made NOT NULL with that default for new rows. 0001 builds a fresh database
from the current models, which already carry all of this, so each step is guarded (0166's idiom). The lists and CHECKs repeat
app.models (test_ccrm_005_migration). The downgrade drops the table and the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0182_lead_data_fields"
down_revision = "0181_lead_meetings"
branch_labels = None
depends_on = None

LEADS, QUALS, TESTS = "enquiries", "lead_qualifications", "lead_english_tests"
CONTACT_PREFERENCES = ("call", "whatsapp", "email", "sms")
STUDY_MODES = ("full_time", "part_time", "online")
ENGLISH_TESTS = ("IELTS", "TOEFL", "PTE", "Duolingo", "Other")
ENGLISH_TEST_STATUSES = ("not_taken", "booked", "taken")
ENQUIRY_DATE_DEFAULT = "(now() AT TIME ZONE 'Asia/Kolkata')::date"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


LEAD_CHECKS = {
    "ck_enquiries_contact_preference": _in("contact_preference", CONTACT_PREFERENCES),
    "ck_enquiries_marketing_consent": "(marketing_opt_in IS NULL) = (marketing_consent_at IS NULL)",
}
QUAL_CHECKS = {
    "ck_lead_qualifications_study_mode": _in("study_mode", STUDY_MODES),
    "ck_lead_qualifications_cgpa": "academic_cgpa IS NULL OR academic_cgpa BETWEEN 0 AND 10",
    "ck_lead_qualifications_backlogs": "backlogs IS NULL OR backlogs BETWEEN 0 AND 99",
}
def lead_columns() -> tuple[sa.Column, ...]:  # fresh objects per call: a Column belongs to one table
    return (
        sa.Column("contact_preference", sa.String(10), nullable=True),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=True),
        sa.Column("marketing_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referral_name", sa.String(160), nullable=True),
        sa.Column("referral_contact", sa.String(120), nullable=True),
    )


def qual_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("preferred_country_id", sa.Uuid(), sa.ForeignKey("countries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("study_mode", sa.String(20), nullable=True),
        sa.Column("preferred_campus", sa.String(200), nullable=True),
        sa.Column("academic_cgpa", sa.Numeric(4, 2), nullable=True),
        sa.Column("backlogs", sa.SmallInteger(), nullable=True),
    )


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything

    def columns(table: str) -> set[str]:
        return set() if inspector is None else {c["name"] for c in inspector.get_columns(table)}

    def checks(table: str) -> set[str]:
        return set() if inspector is None else {c["name"] for c in inspector.get_check_constraints(table)}

    have = columns(LEADS)
    for column in lead_columns():
        if column.name not in have:
            op.add_column(LEADS, column)
    if "enquiry_date" not in have:
        op.add_column(LEADS, sa.Column("enquiry_date", sa.Date(), nullable=True))
        op.execute(f"UPDATE {LEADS} SET enquiry_date = (created_at AT TIME ZONE 'Asia/Kolkata')::date")
        op.alter_column(LEADS, "enquiry_date", nullable=False, server_default=sa.text(ENQUIRY_DATE_DEFAULT))
    for name, sql in LEAD_CHECKS.items():
        if name not in checks(LEADS):
            op.create_check_constraint(name, LEADS, sql)

    have = columns(QUALS)
    for column in qual_columns():
        if column.name not in have:
            op.add_column(QUALS, column)
    for name, sql in QUAL_CHECKS.items():
        if name not in checks(QUALS):
            op.create_check_constraint(name, QUALS, sql)

    if inspector is None or not inspector.has_table(TESTS):
        op.create_table(
            TESTS,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.SmallInteger(), nullable=False),
            sa.Column("test_type", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("overall_score", sa.Numeric(4, 1), nullable=True),
            sa.Column("test_date", sa.Date(), nullable=True),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column("remarks", sa.String(200), nullable=True),
            sa.UniqueConstraint("lead_id", "position", name="uq_lead_english_tests_position"),
            sa.CheckConstraint(f"test_type IN ({', '.join(repr(v) for v in ENGLISH_TESTS)})", name="ck_lead_english_tests_type"),
            sa.CheckConstraint(_in("status", ENGLISH_TEST_STATUSES), name="ck_lead_english_tests_status"),
        )


def downgrade() -> None:
    op.drop_table(TESTS)
    for name in QUAL_CHECKS:
        op.drop_constraint(name, QUALS, type_="check")
    for column in reversed(qual_columns()):
        op.drop_column(QUALS, column.name)
    for name in LEAD_CHECKS:
        op.drop_constraint(name, LEADS, type_="check")
    op.drop_column(LEADS, "enquiry_date")
    for column in reversed(lead_columns()):
        op.drop_column(LEADS, column.name)
