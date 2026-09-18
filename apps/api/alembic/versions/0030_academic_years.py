"""ENH-001 -- add academic_years and SchoolStudent.academic_year_id/grade_level, with backfill.

Revision ID: 0030_academic_years
Revises: 0029_partnership_gaps

docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md. Global (no school_id) per
the user's explicit decision. Adds columns nullable-first (no NOT NULL default on a live
table in one step), then backfills: every existing school_students row gets the seed
AcademicYear, and grade_level is derived from grade_or_class where parseable (left NULL,
never a fabricated sentinel, where it isn't -- spec decision 4).
"""

import re
from datetime import date

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030_academic_years"
down_revision = "0029_partnership_gaps"
branch_labels = None
depends_on = None


def _derive_grade_level(label: str | None) -> int | None:
    if not label:
        return None
    match = re.search(r"\b(?:grade|class)\s*(\d{1,2})\b|\b(\d{1,2})\b", label.lower())
    if not match:
        return None
    value = int(match.group(1) or match.group(2))
    return value if 1 <= value <= 12 else None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "academic_years" not in inspector.get_table_names():
        op.create_table(
            "academic_years",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("label", sa.String(20), nullable=False, unique=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    existing_columns = {c["name"] for c in inspector.get_columns("school_students")}
    if "academic_year_id" not in existing_columns:
        op.add_column("school_students", sa.Column("academic_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("academic_years.id"), nullable=True))
        op.create_index("ix_school_students_academic_year_id", "school_students", ["academic_year_id"])
    if "grade_level" not in existing_columns:
        op.add_column("school_students", sa.Column("grade_level", sa.Integer(), nullable=True))

    # Seed row: today's academic year, so there's something to backfill onto immediately.
    seed_id = str(op.get_bind().execute(sa.text("SELECT gen_random_uuid()")).scalar())
    today = date.today()
    # Indian academic-year convention (School CRM.md's own examples: "2026-27") -- April to
    # March. Review finding: the backlog's own "Edge cases" section marks whether every
    # school follows this convention (vs. international/CBSE-vs-state variance) as
    # genuinely NEEDS_CONFIRMATION, not decided -- this is a real, disclosed assumption,
    # not a confirmed business rule. Do not read the code below as settling that question;
    # it's the placeholder the unconfirmed scope decision (`DEC-DATA-0xx`) still needs to
    # either ratify or replace.
    start_year = today.year if today.month >= 4 else today.year - 1
    label = f"{start_year}-{str(start_year + 1)[-2:]}"
    existing_seed = bind.execute(sa.text("SELECT id FROM academic_years WHERE label = :label"), {"label": label}).fetchone()
    if not existing_seed:
        bind.execute(
            sa.text("INSERT INTO academic_years (id, label, start_date, end_date, status, created_at, updated_at) VALUES (:id, :label, :start, :end, 'active', now(), now())"),
            {"id": seed_id, "label": label, "start": date(start_year, 4, 1), "end": date(start_year + 1, 3, 31)},
        )
        current_id = seed_id
    else:
        current_id = str(existing_seed[0])

    bind.execute(sa.text("UPDATE school_students SET academic_year_id = :year_id WHERE academic_year_id IS NULL"), {"year_id": current_id})

    rows = bind.execute(sa.text("SELECT id, student_code, grade_or_class FROM school_students WHERE grade_level IS NULL")).fetchall()
    unparseable_codes = []
    for row_id, student_code, grade_or_class in rows:
        derived = _derive_grade_level(grade_or_class)
        if derived is None:
            # Review finding fix: log which row, not just how many -- an aggregate count
            # gives an operator nothing to act on. `student_code` is this table's
            # human-readable natural key, so "needs manual coordinator follow-up" is
            # actually followable.
            unparseable_codes.append(student_code)
            continue
        bind.execute(sa.text("UPDATE school_students SET grade_level = :g WHERE id = :id"), {"g": derived, "id": row_id})
    if unparseable_codes:
        print(f"[0030_academic_years] {len(unparseable_codes)} school_students row(s) had an unparseable grade_or_class -- grade_level left NULL, needs manual coordinator follow-up: {', '.join(unparseable_codes)}")


def downgrade() -> None:
    op.drop_index("ix_school_students_academic_year_id", table_name="school_students")
    op.drop_column("school_students", "academic_year_id")
    op.drop_column("school_students", "grade_level")
    op.drop_table("academic_years")
