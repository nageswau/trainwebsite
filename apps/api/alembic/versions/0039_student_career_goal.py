"""ENH-013 -- school_students.career_goal.

Revision ID: 0039_student_career_goal
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §5. Add-column only: nullable, no default, no
backfill, so no existing row is read or rewritten (a metadata-only change on PostgreSQL). `downgrade()` drops the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0039_student_career_goal"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent, like 0035: `0001_initial` builds tables from the *current* models (`Base.metadata.create_all`), and dev
    # startup can too, so on a from-scratch replay the column already exists here (caught by test_enh_001's isolated
    # full-history replay). Skipped when Alembic only renders SQL (`--sql`), where there is no connection to inspect.
    if not op.get_context().as_sql and "career_goal" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("school_students")}:
        return
    op.add_column("school_students", sa.Column("career_goal", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("school_students", "career_goal")
