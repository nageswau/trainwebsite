"""ccrm-007 -- the structured overseas student profile, its qualifications and English tests.

Revision ID: 0174_student_profiles
Revises: 0173_checklist_templates

docs/superpowers/specs/2026-10-24-ccrm-007-structured-student-profile-design.md (DEC-SCOPE-249). 0001 builds a fresh database from the
current models, which already carry the tables, so they are created only when missing (0166's idiom). Then, once per overseas student
without a profile (P4), the old free-text `users.profile` keys are copied: `preferred_countries` names -> country ids (case-insensitive,
unmatched names dropped), `preferred_intake`, `education` -> one qualification (level `other`), `english_test` -> one test (type read
from the text, else `Other`; no status; the text kept in `remarks`). The JSON itself is never changed. The constants repeat
app.models (test_ccrm_007_migration).
"""

import json
import uuid

import sqlalchemy as sa

from alembic import op

revision = "0174_student_profiles"
down_revision = "0173_checklist_templates"
branch_labels = None
depends_on = None

PROFILES, QUALIFICATIONS, TESTS = "overseas_student_profiles", "overseas_student_qualifications", "overseas_student_english_tests"
LEVELS = ("UG", "PG", "PhD", "Diploma", "Foundation")
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")
STUDY_MODES = ("full_time", "part_time", "online")
QUALIFICATION_LEVELS = ("class_10", "class_12", "diploma", "bachelor", "master", "phd", "other")
SCORE_TYPES = ("percentage", "cgpa")
TEST_TYPES = ("IELTS", "TOEFL", "PTE", "Duolingo", "Other")
TEST_STATUSES = ("not_taken", "booked", "taken")
LEGACY_KEYS = ("education", "preferred_countries", "preferred_intake", "english_test")


def _in(column: str, values: tuple[str, ...], nullable: bool = True) -> str:
    listed = f"{column} IN ({', '.join(repr(v) for v in values)})"
    return f"{column} IS NULL OR {listed}" if nullable else listed


def _missing() -> bool:
    return op.get_context().as_sql or PROFILES not in sa.inspect(op.get_bind()).get_table_names()


def _text(value, limit: int) -> str | None:
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _test_type(text: str) -> str:
    lowered = text.lower()
    return next((t for t in TEST_TYPES[:-1] if t.lower() in lowered), "Other")


def _create_tables() -> None:
    op.create_table(
        PROFILES,
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("passport_number", sa.String(20), nullable=True),
        sa.Column("passport_expiry", sa.Date(), nullable=True),
        sa.Column("work_experience_months", sa.SmallInteger(), nullable=True),
        sa.Column("work_experience_details", sa.Text(), nullable=True),
        sa.Column("preferred_country_ids", sa.JSON(), nullable=False),
        sa.Column("preferred_course", sa.String(200), nullable=True),
        sa.Column("preferred_level", sa.String(20), nullable=True),
        sa.Column("preferred_intake", sa.String(40), nullable=True),
        sa.Column("study_mode", sa.String(20), nullable=True),
        sa.Column("budget_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_currency", sa.String(3), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("preferred_level", LEVELS), name="ck_overseas_student_profiles_level"),
        sa.CheckConstraint(_in("study_mode", STUDY_MODES), name="ck_overseas_student_profiles_study_mode"),
        sa.CheckConstraint(_in("budget_currency", CURRENCIES), name="ck_overseas_student_profiles_currency"),
        sa.CheckConstraint("work_experience_months IS NULL OR work_experience_months BETWEEN 0 AND 600", name="ck_overseas_student_profiles_experience"),
    )
    op.create_table(
        QUALIFICATIONS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey(f"{PROFILES}.student_user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("qualification_name", sa.String(200), nullable=True),
        sa.Column("institution", sa.String(200), nullable=True),
        sa.Column("board_university", sa.String(200), nullable=True),
        sa.Column("year_completed", sa.SmallInteger(), nullable=True),
        sa.Column("score_type", sa.String(20), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("backlogs", sa.SmallInteger(), nullable=True),
        sa.UniqueConstraint("student_user_id", "position", name="uq_overseas_student_qualifications_position"),
        sa.CheckConstraint(_in("level", QUALIFICATION_LEVELS, nullable=False), name="ck_overseas_student_qualifications_level"),
        sa.CheckConstraint(_in("score_type", SCORE_TYPES), name="ck_overseas_student_qualifications_score_type"),
    )
    op.create_table(
        TESTS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey(f"{PROFILES}.student_user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("test_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("overall_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("test_date", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("remarks", sa.String(200), nullable=True),
        sa.UniqueConstraint("student_user_id", "position", name="uq_overseas_student_english_tests_position"),
        sa.CheckConstraint(_in("test_type", TEST_TYPES, nullable=False), name="ck_overseas_student_english_tests_type"),
        sa.CheckConstraint(_in("status", TEST_STATUSES), name="ck_overseas_student_english_tests_status"),
    )


def _copy_legacy_profiles() -> None:
    bind = op.get_bind()
    countries = {name.strip().lower(): str(cid) for cid, name in bind.execute(sa.text("SELECT id, name FROM countries"))}
    students = bind.execute(sa.text(f"SELECT u.id, u.profile FROM users u WHERE u.role = 'overseas_student' AND NOT EXISTS (SELECT 1 FROM {PROFILES} p WHERE p.student_user_id = u.id)")).all()
    for student_id, raw in students:
        legacy = (json.loads(raw) if isinstance(raw, str) else raw) or {}
        if not isinstance(legacy, dict) or not any(legacy.get(k) for k in LEGACY_KEYS):
            continue
        names = legacy.get("preferred_countries") if isinstance(legacy.get("preferred_countries"), list) else []
        country_ids = list(dict.fromkeys(countries[n.strip().lower()] for n in names if isinstance(n, str) and n.strip().lower() in countries))[:5]
        bind.execute(
            sa.text(f"INSERT INTO {PROFILES} (student_user_id, preferred_country_ids, preferred_intake) VALUES (:id, CAST(:countries AS JSON), :intake)"),
            {"id": student_id, "countries": json.dumps(country_ids), "intake": _text(legacy.get("preferred_intake"), 40)},
        )
        education = _text(legacy.get("education"), 200)
        if education:
            bind.execute(
                sa.text(f"INSERT INTO {QUALIFICATIONS} (id, student_user_id, position, level, qualification_name) VALUES (:id, :s, 0, 'other', :name)"),
                {"id": uuid.uuid4(), "s": student_id, "name": education},
            )
        english = _text(legacy.get("english_test"), 200)
        if english:
            bind.execute(
                sa.text(f"INSERT INTO {TESTS} (id, student_user_id, position, test_type, remarks) VALUES (:id, :s, 0, :type, :remarks)"),
                {"id": uuid.uuid4(), "s": student_id, "type": _test_type(english), "remarks": english},
            )


def upgrade() -> None:
    if _missing():
        _create_tables()
    if not op.get_context().as_sql:
        _copy_legacy_profiles()


def downgrade() -> None:
    op.drop_table(TESTS)
    op.drop_table(QUALIFICATIONS)
    op.drop_table(PROFILES)
