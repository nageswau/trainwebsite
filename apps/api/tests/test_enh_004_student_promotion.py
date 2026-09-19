"""ENH-004 -- Student promotion to the next academic year / grade
(docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md, DEC-SCOPE-020)."""

import asyncio
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.schools import (
    MAX_GRADE_LEVEL,
    REASON_ALREADY_IN_ACTIVE_YEAR,
    REASON_GRADE_LEVEL_NOT_SET,
    REASON_LABEL_UNPARSEABLE,
    REASON_TERMINAL_GRADE,
    _decide_promotion,
    _swap_grade_label,
)
from app.core.config import settings
from app.models import SchoolStudentGradeHistory
from app.schemas import StudentPromotionRequest

YEAR_OLD = uuid.uuid4()
YEAR_ACTIVE = uuid.uuid4()


# ---------------------------------------------------------------- label swap (pure)


@pytest.mark.parametrize(
    "label,from_level,to_level,expected",
    [
        ("Grade 8-A", 8, 9, "Grade 9-A"),
        ("Class 10", 10, 11, "Class 11"),
        ("grade 5", 5, 6, "grade 6"),
        ("10-A", 10, 11, "11-A"),
        ("Grade 9", 9, 10, "Grade 10"),
        ("Grade 11 (Gold)", 11, 12, "Grade 12 (Gold)"),
    ],
)
def test_swap_grade_label_advances_only_the_grade_number(label, from_level, to_level, expected):
    assert _swap_grade_label(label, from_level, to_level) == (expected, None)


def test_swap_grade_label_leaves_a_missing_label_missing():
    assert _swap_grade_label(None, 8, 9) == (None, None)


@pytest.mark.parametrize("label", ["8A", "Nonsense", "Std IX", ""])
def test_swap_grade_label_refuses_a_label_without_a_grade_number(label):
    new_label, problem = _swap_grade_label(label, 8, 9)
    assert new_label is None
    assert problem and "supply grade_or_class" in problem


def test_swap_grade_label_refuses_a_number_that_disagrees_with_grade_level():
    new_label, problem = _swap_grade_label("Grade 8-A", 9, 10)
    assert new_label is None
    assert problem and "does not match" in problem


def test_swap_grade_label_refuses_a_result_longer_than_60_characters():
    label = "Grade 9 " + "x" * 52  # exactly 60 characters; "9" -> "10" would make it 61
    assert len(label) == 60
    new_label, problem = _swap_grade_label(label, 9, 10)
    assert new_label is None
    assert problem and "60 characters" in problem


# ---------------------------------------------------------------- per-row decision (pure)


def _decide(**overrides):
    args = {"action": "promote", "student_year_id": YEAR_OLD, "active_year_id": YEAR_ACTIVE, "grade_level": 8, "grade_or_class": "Grade 8-A", "override": None}
    args.update(overrides)
    return _decide_promotion(**args)


def test_promote_advances_the_level_and_the_label():
    d = _decide()
    assert (d.status, d.grade_level, d.grade_or_class, d.reason, d.message) == ("promoted", 9, "Grade 9-A", None, None)


def test_promote_uses_the_override_instead_of_the_swap():
    d = _decide(override="Grade 9 (Gold)")
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, "Grade 9 (Gold)")


def test_promote_with_no_label_keeps_no_label():
    d = _decide(grade_or_class=None)
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, None)


def test_hold_back_keeps_grade_and_label():
    d = _decide(action="hold_back")
    assert (d.status, d.grade_level, d.grade_or_class, d.reason) == ("held_back", 8, "Grade 8-A", None)


@pytest.mark.parametrize("grade_level", [12, None])
def test_hold_back_is_allowed_at_the_top_grade_and_with_no_grade(grade_level):
    d = _decide(action="hold_back", grade_level=grade_level)
    assert (d.status, d.grade_level) == ("held_back", grade_level)


@pytest.mark.parametrize("action", ["promote", "hold_back"])
def test_a_student_already_in_the_active_year_is_skipped_and_unchanged(action):
    d = _decide(action=action, student_year_id=YEAR_ACTIVE)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("skipped", REASON_ALREADY_IN_ACTIVE_YEAR, 8, "Grade 8-A")
    assert d.message


def test_a_student_with_no_year_is_processable():
    assert _decide(student_year_id=None).status == "promoted"


def test_promote_without_a_grade_level_fails():
    d = _decide(grade_level=None)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_GRADE_LEVEL_NOT_SET, None, "Grade 8-A")


def test_promote_from_the_top_grade_fails():
    assert MAX_GRADE_LEVEL == 12
    d = _decide(grade_level=12, grade_or_class="Grade 12")
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_TERMINAL_GRADE, 12, "Grade 12")


def test_promote_with_an_unswappable_label_fails_unless_overridden():
    failed = _decide(grade_or_class="8A")
    assert (failed.status, failed.reason, failed.grade_level, failed.grade_or_class) == ("failed", REASON_LABEL_UNPARSEABLE, 8, "8A")
    assert failed.message
    fixed = _decide(grade_or_class="8A", override="Grade 9A")
    assert (fixed.status, fixed.grade_level, fixed.grade_or_class) == ("promoted", 9, "Grade 9A")


# ---------------------------------------------------------------- request model (pure)


def _item(**overrides):
    return {"student_id": str(uuid.uuid4()), "action": "promote", **overrides}


def test_request_accepts_valid_items():
    request = StudentPromotionRequest(items=[_item(), _item(action="hold_back")])
    assert [i.action for i in request.items] == ["promote", "hold_back"]


def test_request_strips_the_override_label():
    request = StudentPromotionRequest(items=[_item(grade_or_class="  Grade 9-A  ")])
    assert request.items[0].grade_or_class == "Grade 9-A"


_DUPLICATE = _item()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [_item() for _ in range(501)]},
        {"items": [_DUPLICATE, _DUPLICATE]},
        {"items": [_item(student_id="not-a-uuid")]},
        {"items": [_item(action="graduate")]},
        {"items": [_item(action="hold_back", grade_or_class="Grade 9")]},
        {"items": [_item(grade_or_class="   ")]},
        {"items": [_item(grade_or_class="x" * 61)]},
        {"items": [_item(grade_or_class="Grade\x00 9")]},
        {"items": [_item(grade_or_class="Grade\n9")]},
        {"items": [_item()], "school_id": str(uuid.uuid4())},
        {"items": [_item(academic_year_id=str(uuid.uuid4()))]},
    ],
    ids=[
        "missing_items", "empty_items", "over_the_cap", "duplicate_id", "not_a_uuid", "unknown_action", "hold_back_with_label", "blank_label", "label_too_long",
        "nul_in_label", "newline_in_label", "client_supplied_school_id", "client_supplied_year_on_item",
    ],
)
def test_request_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        StudentPromotionRequest(**payload)


# ---------------------------------------------------------------- model + migration

API_ROOT = Path(__file__).resolve().parents[1]
HISTORY_TABLE_COUNT_SQL = "SELECT count(*) FROM information_schema.tables WHERE table_name = 'school_student_grade_history'"


def test_grade_history_model_shape():
    table = SchoolStudentGradeHistory.__table__
    assert table.name == "school_student_grade_history"
    for name in ("school_student_id", "action", "to_academic_year_id", "performed_by_user_id"):
        assert table.columns[name].nullable is False, name
    for name in ("from_academic_year_id", "from_grade_level", "from_grade_or_class", "to_grade_level", "to_grade_or_class"):
        assert table.columns[name].nullable is True, name
    assert table.columns["from_grade_or_class"].type.length == 60
    assert "uq_school_student_grade_history_year" in {c.name for c in table.constraints}


def _sql(url: str, statement: str, params: dict | None = None, *, autocommit: bool = False) -> list:
    """Run one statement on its own throwaway engine. A plain (sync) helper on purpose: alembic's
    env.py calls asyncio.run() itself, so the migration test cannot run inside an event loop."""

    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(sa.text(statement), params or {})
                rows = result.fetchall() if result.returns_rows else []
                await conn.commit()
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@contextmanager
def _isolated_migration_database():
    """A uniquely named, throwaway database (never the shared one -- ENH-001's review found a real
    downgrade destroying live rows). Yields (alembic Config, isolated URL); always drops it."""
    original_url = settings.database_url
    name = f"enh004_migration_isolated_{uuid.uuid4().hex[:8]}"
    isolated_url = make_url(original_url).set(database=name).render_as_string(hide_password=False)
    _sql(original_url, f'CREATE DATABASE "{name}"', autocommit=True)
    settings.database_url = isolated_url
    try:
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        yield cfg, isolated_url
    finally:
        settings.database_url = original_url
        try:
            _sql(original_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
        except Exception:
            pass  # best-effort: a leftover uniquely named throwaway database is a contained cost


def test_migration_0033_creates_and_drops_only_the_history_table_and_keeps_student_rows():
    creator_id, school_id, student_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    unique = uuid.uuid4().hex[:8]
    with _isolated_migration_database() as (cfg, url):
        command.upgrade(cfg, "0032_welcome_token_purpose")
        # `0001_initial` builds the baseline from the *current* ORM metadata, so on a fresh database the table
        # already exists by 0032 (which is why every migration here is inspector-guarded, and why 0033 is a
        # no-op there). A real database created before this feature has no such table: emulate that state.
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 1
        _sql(url, "DROP TABLE school_student_grade_history")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 0
        # Raw SQL against the pre-0033 schema (same column list ENH-001's migration test uses; `users` is unchanged since 0028).
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, phone, active, email_verified, locale, profile, student_code) "
            "VALUES (:id, :email, 'x', 'Cycle Admin', 'overseas_admin', 'overseas', NULL, true, true, 'en-GB', '{}', NULL)",
            {"id": creator_id, "email": f"enh004-cycle-{unique}@example.local"},
        )
        _sql(url, "INSERT INTO schools (id, name, created_by_user_id) VALUES (:id, 'ENH-004 Cycle School', :creator)", {"id": school_id, "creator": creator_id})
        _sql(
            url,
            "INSERT INTO school_students (id, school_id, student_code, full_name, grade_or_class, grade_level, created_by_user_id) VALUES (:id, :school, :code, 'Cycle Student', 'Grade 8', 8, :creator)",
            {"id": student_id, "school": school_id, "code": f"E{unique[:7]}".upper(), "creator": creator_id},
        )

        command.upgrade(cfg, "0033_student_grade_history")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 1
        year_id = _sql(url, "SELECT id FROM academic_years ORDER BY start_date DESC LIMIT 1")[0][0]
        insert = "INSERT INTO school_student_grade_history (id, school_student_id, action, to_academic_year_id, performed_by_user_id) VALUES (:id, :student, 'held_back', :year, :creator)"
        _sql(url, insert, {"id": uuid.uuid4(), "student": student_id, "year": year_id, "creator": creator_id})
        with pytest.raises(IntegrityError, match="uq_school_student_grade_history_year"):
            _sql(url, insert, {"id": uuid.uuid4(), "student": student_id, "year": year_id, "creator": creator_id})

        command.downgrade(cfg, "0032_welcome_token_purpose")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 0
        assert _sql(url, "SELECT full_name, grade_level FROM school_students WHERE id = :id", {"id": student_id}) == [("Cycle Student", 8)]


@pytest.mark.asyncio
async def test_the_shared_database_has_the_history_table(db_session):
    # Fails until migration 0033 has been applied to the test database.
    result = await db_session.execute(text(HISTORY_TABLE_COUNT_SQL))
    assert result.scalar() == 1
