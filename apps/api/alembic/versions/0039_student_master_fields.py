"""ENH-025 -- Student Master fields on school_students, class details on the grade-history ledger.

Revision ID: 0039_student_master_fields
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §2 (DEC-SCOPE-027). Additive only:
nullable columns, a CHECK on gender, a partial unique index on roll numbers, and a backfill of `section`
from `grade_or_class` where the label unambiguously ends in a section letter. `grade_or_class` is read,
never written. Unparseable labels leave `section` NULL (never guessed) and their student codes are printed,
same as 0030. `downgrade()` drops everything this adds.

If ENH-013's `0039_student_career_goal` (also on 0038) merges first, rename this file and re-chain
`down_revision` -- the later-merging branch moves (precedent: 0038_portfolio's own re-chain note).
"""

import re

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_student_master_fields"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None

STUDENT_COLUMNS = (
    ("section", sa.String(20)), ("roll_number", sa.String(20)), ("gender", sa.String(20)),
    ("student_mobile", sa.String(20)), ("city", sa.String(120)),
    ("subjects", postgresql.JSON()), ("career_interests", postgresql.JSON()),
    ("global_education_interest", sa.Boolean()),
    ("preferred_countries", postgresql.JSON()), ("preferred_courses", postgresql.JSON()),
    ("photo_key", sa.String(200)), ("photo_content_type", sa.String(40)),
)
HISTORY_COLUMNS = (("from_section", sa.String(20)), ("from_roll_number", sa.String(20)), ("to_section", sa.String(20)))
GENDER_CHECK = "gender IS NULL OR gender IN ('female', 'male', 'other', 'prefer_not_to_say')"

# A grade number, then an optional separator (-, /, spaces) or the word "section", then 1-2 letters that end
# the label: "10-A", "Grade 8-A", "Class 7 Section C", "9B". Ordinal suffixes ("10th") are not sections.
_SECTION = re.compile(r"\d{1,2}\s*(?:section\s+|[-/]\s*)?([a-z]{1,2})\s*$", re.IGNORECASE)
_ORDINALS = {"st", "nd", "rd", "th"}


def _derive_section(label: str | None) -> str | None:
    if not label or not label.strip():
        return None
    match = _SECTION.search(label.strip())
    if not match or match.group(1).lower() in _ORDINALS:
        return None
    return match.group(1)


def upgrade() -> None:
    # Every step is guarded: on a fresh database 0001_initial's Base.metadata.create_all() has already built
    # school_students from the *current* models (columns, CHECK and index included), same reason 0030 guards.
    bind = op.get_bind()
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(bind)
    existing = set() if offline else {c["name"] for c in inspector.get_columns("school_students")}
    for name, type_ in STUDENT_COLUMNS:
        if name not in existing:
            op.add_column("school_students", sa.Column(name, type_, nullable=True))
    existing_history = set() if offline else {c["name"] for c in inspector.get_columns("school_student_grade_history")}
    for name, type_ in HISTORY_COLUMNS:
        if name not in existing_history:
            op.add_column("school_student_grade_history", sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("school_students")}
    if "ck_school_students_gender" not in checks:
        op.create_check_constraint("ck_school_students_gender", "school_students", GENDER_CHECK)

    if not offline:
        rows = bind.execute(sa.text("SELECT id, student_code, grade_or_class FROM school_students WHERE section IS NULL AND grade_or_class IS NOT NULL")).fetchall()
        unparsed = []
        for row_id, student_code, label in rows:
            section = _derive_section(label)
            if section is None:
                unparsed.append(student_code)
                continue
            bind.execute(sa.text("UPDATE school_students SET section = :section WHERE id = :id"), {"section": section, "id": row_id})
        if unparsed:
            print(f"[0039_student_master_fields] {len(unparsed)} school_students row(s) had no parseable section in grade_or_class -- section left NULL: {', '.join(unparsed)}")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_school_students_roll ON school_students "
        "(school_id, academic_year_id, grade_level, lower(section), roll_number) NULLS NOT DISTINCT "
        "WHERE roll_number IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_school_students_roll")
    op.execute("ALTER TABLE school_students DROP CONSTRAINT IF EXISTS ck_school_students_gender")
    for name, _ in HISTORY_COLUMNS:
        op.drop_column("school_student_grade_history", name)
    for name, _ in STUDENT_COLUMNS:
        op.drop_column("school_students", name)
