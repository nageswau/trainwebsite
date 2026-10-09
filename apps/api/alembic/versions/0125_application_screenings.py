"""rec-018 -- application_screenings.

Revision ID: 0125_application_screenings
Revises: 0124_university_documents

docs/superpowers/specs/2026-10-09-rec-018-application-screening-design.md §1 (DEC-SCOPE-140). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0122's idiom).
CHECKS repeats app.models.SCREENING_CHECKS (test_rec_018_migration). downgrade() refuses while any row exists: entered data is never
dropped silently.

Drafted on `0122_candidate_skills`; re-chained on 2026-10-09 after rec-010 (`0123_candidate_consents`) and upc-026
(`0124_university_documents`) merged first. The number, DEC-SCOPE-140, §12BH and §2.66 were already the next free set, so only
`down_revision` changed. A database stamped at the draft is re-stamped with `alembic stamp --purge 0122_candidate_skills`, then
`upgrade head` (the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0125_application_screenings"
down_revision = "0124_university_documents"
branch_labels = None
depends_on = None

TABLE = "application_screenings"
UUID = postgresql.UUID(as_uuid=True)
RESULTS = ("shortlisted", "hold", "rejected", "need_more_info")

CHECKS = {  # must equal app.models.SCREENING_CHECKS (test_rec_018_migration)
    "ck_application_screenings_result": "result IN (" + ", ".join(f"'{r}'" for r in RESULTS) + ")",
    "ck_application_screenings_rejected_remarks": "result <> 'rejected' OR remarks IS NOT NULL",
    "ck_application_screenings_communication": "communication_rating IS NULL OR communication_rating BETWEEN 1 AND 5",
    "ck_application_screenings_technical": "technical_rating IS NULL OR technical_rating BETWEEN 1 AND 5",
    "ck_application_screenings_notice": "notice_days IS NULL OR notice_days BETWEEN 0 AND 365",
    "ck_application_screenings_salary": "expected_salary IS NULL OR expected_salary >= 0",
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def flag(name: str) -> sa.Column:
        return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false"))

    op.create_table(
        TABLE,
        sa.Column("application_id", UUID, sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), primary_key=True),
        flag("qualification_verified"),
        flag("experience_verified"),
        flag("skills_verified"),
        sa.Column("expected_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("notice_days", sa.SmallInteger(), nullable=True),
        sa.Column("location_preference", sa.String(200), nullable=True),
        sa.Column("communication_rating", sa.SmallInteger(), nullable=True),
        sa.Column("technical_rating", sa.SmallInteger(), nullable=True),
        sa.Column("availability", sa.String(120), nullable=True),
        sa.Column("willing_to_relocate", sa.Boolean(), nullable=True),
        sa.Column("remarks", sa.String(2000), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("screened_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0125_application_screenings: screenings exist. Clear them deliberately first.")
    op.drop_table(TABLE)
