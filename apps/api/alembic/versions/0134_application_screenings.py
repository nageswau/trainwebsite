"""rec-018 -- application_screenings.

Revision ID: 0134_application_screenings
Revises: 0133_interview_management

docs/superpowers/specs/2026-10-09-rec-018-application-screening-design.md §1 (DEC-SCOPE-149). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0122's idiom).
CHECKS repeats app.models.SCREENING_CHECKS (test_rec_018_migration). downgrade() refuses while any row exists: entered data is never
dropped silently.

Re-chained on 2026-10-09: drafted as `0125_application_screenings` (DEC-SCOPE-140, API §12BH, RBAC §2.66) on `0122_candidate_skills`,
then `0126` (141 / §12BI / §2.67) after upc-012. rec-010, upc-026, upc-012 and then the upc items through `0132` and rec-020
(`0133_interview_management`, DEC-SCOPE-148) merged first, so this is `0134` (DEC-SCOPE-149, §12BQ, §2.75). A database stamped at an
earlier draft is re-stamped with `alembic stamp --purge <that draft's down_revision>`, then `upgrade head` (the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0134_application_screenings"
down_revision = "0133_interview_management"
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
        raise RuntimeError("Cannot downgrade 0134_application_screenings: screenings exist. Clear them deliberately first.")
    op.drop_table(TABLE)
