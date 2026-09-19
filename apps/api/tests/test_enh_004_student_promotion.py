"""ENH-004 -- Student promotion to the next academic year / grade
(docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md, DEC-SCOPE-020)."""

import asyncio
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
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
from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    AcademicYear,
    AuditLog,
    School,
    SchoolParentLink,
    SchoolStudent,
    SchoolStudentGradeHistory,
    User,
    UserRoleAssignment,
)
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


def _raw_item(**overrides):
    return {"student_id": str(uuid.uuid4()), "action": "promote", **overrides}


def test_request_accepts_valid_items():
    request = StudentPromotionRequest(items=[_raw_item(), _raw_item(action="hold_back")])
    assert [i.action for i in request.items] == ["promote", "hold_back"]


def test_request_strips_the_override_label():
    request = StudentPromotionRequest(items=[_raw_item(grade_or_class="  Grade 9-A  ")])
    assert request.items[0].grade_or_class == "Grade 9-A"


_DUPLICATE = _raw_item()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [_raw_item() for _ in range(501)]},
        {"items": [_DUPLICATE, _DUPLICATE]},
        {"items": [_raw_item(student_id="not-a-uuid")]},
        {"items": [_raw_item(action="graduate")]},
        {"items": [_raw_item(action="hold_back", grade_or_class="Grade 9")]},
        {"items": [_raw_item(grade_or_class="   ")]},
        {"items": [_raw_item(grade_or_class="x" * 61)]},
        {"items": [_raw_item(grade_or_class="Grade\x00 9")]},
        {"items": [_raw_item(grade_or_class="Grade\n9")]},
        {"items": [_raw_item()], "school_id": str(uuid.uuid4())},
        {"items": [_raw_item(academic_year_id=str(uuid.uuid4()))]},
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
    # alembic/env.py calls logging.config.fileConfig(), whose default is to DISABLE every existing logger; left
    # alone that silences `app.school` for every later test in the session. Snapshot and restore the flags.
    logger_state = {n: lg.disabled for n, lg in logging.Logger.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    _sql(original_url, f'CREATE DATABASE "{name}"', autocommit=True)
    settings.database_url = isolated_url
    try:
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        yield cfg, isolated_url
    finally:
        for logger_name, was_disabled in logger_state.items():
            logging.getLogger(logger_name).disabled = was_disabled
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


# ---------------------------------------------------------------- endpoint helpers

PASSWORD = "Sup3r-Secret-Pass!"
URL = "/api/v1/school/students/promotions"


@pytest_asyncio.fixture
async def future_years(db_session):
    """Factory for ACTIVE academic years dated far in the future, so they win
    `_current_academic_year_id`'s latest-start_date tie-break without ever touching a real year
    (the same technique as test_enh_001's active-year test). Everything the tests attach to them is
    removed afterwards so repeated runs against the shared database stay idempotent."""
    created: list[uuid.UUID] = []

    async def _make(start: date = date(9999, 4, 1)) -> AcademicYear:
        year = AcademicYear(label=f"enh004-{uuid.uuid4().hex[:8]}", start_date=start, end_date=date(9999, 12, 30), status="active")
        db_session.add(year)
        await db_session.commit()
        created.append(year.id)
        return year

    yield _make

    if created:
        await db_session.rollback()
        await db_session.execute(delete(SchoolStudentGradeHistory).where(or_(SchoolStudentGradeHistory.to_academic_year_id.in_(created), SchoolStudentGradeHistory.from_academic_year_id.in_(created))))
        await db_session.execute(update(SchoolStudent).where(SchoolStudent.academic_year_id.in_(created)).values(academic_year_id=None))
        await db_session.execute(delete(AcademicYear).where(AcademicYear.id.in_(created)))
        await db_session.commit()


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200, response.text


async def _user(db_session, *, role: str, full_name: str, school_id=None, assigned_by=None) -> User:
    profile = {"school_id": str(school_id)} if school_id else {}
    u = User(email=f"enh004-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division="overseas", active=True, profile=profile)
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=(assigned_by or u).id, approval_status="approved"))
    return u


async def _school(db_session, students=(("Grade 8-A", 8), ("Grade 8-B", 8))) -> dict:
    """A fresh school with a coordinator, teacher, principal, a parent linked to the first student,
    and one student per (label, grade_level) pair. Students start with academic_year_id NULL, so
    they are processable once an active year exists. The teacher is assigned to the first student only."""
    admin = await _user(db_session, role="overseas_admin", full_name="Overseas Admin")
    school = School(name=f"ENH-004 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = await _user(db_session, role="school_coordinator", full_name="Coordinator", school_id=school.id, assigned_by=admin)
    teacher = await _user(db_session, role="school_teacher", full_name="Ms Teacher", school_id=school.id, assigned_by=coordinator)
    principal = await _user(db_session, role="school_principal", full_name="Principal", school_id=school.id, assigned_by=coordinator)
    rows = []
    for index, (label, level) in enumerate(students):
        rows.append(
            SchoolStudent(
                school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name=f"Child {index}",
                grade_or_class=label, grade_level=level, created_by_user_id=coordinator.id, assigned_teacher_user_id=teacher.id if index == 0 else None,
            )
        )
    db_session.add_all(rows)
    await db_session.flush()
    parent = await _user(db_session, role="school_parent", full_name="Parent of Child 0", school_id=school.id, assigned_by=coordinator)
    db_session.add(SchoolParentLink(parent_user_id=parent.id, school_student_id=rows[0].id, linked_by_user_id=coordinator.id))
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "teacher": teacher, "principal": principal, "parent": parent, "students": rows}


def _item(student, action: str = "promote", **extra) -> dict:
    return {"student_id": str(student.id), "action": action, **extra}


async def _promote(client, items: list[dict]):
    return await client.post(URL, json={"items": items})


async def _history(db_session, student) -> list[SchoolStudentGradeHistory]:
    return list((await db_session.scalars(select(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id == student.id))).all())


# ---------------------------------------------------------------- endpoint: happy paths


@pytest.mark.asyncio
async def test_promote_single_student_advances_grade_label_year_and_records_history(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["academic_year"] == {"id": str(year.id), "label": year.label}
    assert body["counts"] == {"promoted": 1, "held_back": 0, "failed": 0, "skipped": 0}
    assert body["results"] == [{"student_id": str(student.id), "status": "promoted", "reason": None, "message": None, "grade_level": 9, "grade_or_class": "Grade 9-A"}]
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class, student.academic_year_id) == (9, "Grade 9-A", year.id)
    rows = await _history(db_session, student)
    assert len(rows) == 1
    row = rows[0]
    assert (row.action, row.from_academic_year_id, row.from_grade_level, row.from_grade_or_class) == ("promoted", None, 8, "Grade 8-A")
    assert (row.to_academic_year_id, row.to_grade_level, row.to_grade_or_class, row.performed_by_user_id) == (year.id, 9, "Grade 9-A", ctx["coordinator"].id)


@pytest.mark.asyncio
async def test_bulk_promote_records_one_history_row_per_student(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8-A", 8), ("Grade 8-B", 8), ("Class 10", 10)))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(s) for s in ctx["students"]])

    assert response.status_code == 200, response.text
    assert response.json()["counts"] == {"promoted": 3, "held_back": 0, "failed": 0, "skipped": 0}
    for student, expected in zip(ctx["students"], [(9, "Grade 9-A"), (9, "Grade 9-B"), (11, "Class 11")], strict=True):
        await db_session.refresh(student)
        assert (student.grade_level, student.grade_or_class) == expected
    total = await db_session.scalar(select(func.count()).select_from(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id.in_([s.id for s in ctx["students"]])))
    assert total == 3


@pytest.mark.asyncio
async def test_hold_back_moves_the_year_but_keeps_grade_and_records_history(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student, "hold_back")])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "held_back"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class, student.academic_year_id) == (8, "Grade 8-A", year.id)
    row = (await _history(db_session, student))[0]
    assert (row.action, row.from_grade_level, row.to_grade_level, row.from_grade_or_class, row.to_grade_or_class, row.to_academic_year_id) == ("held_back", 8, 8, "Grade 8-A", "Grade 8-A", year.id)


@pytest.mark.asyncio
async def test_an_override_label_wins_over_the_swap(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student, grade_or_class="Grade 9 (Gold)")])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["grade_or_class"] == "Grade 9 (Gold)"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (9, "Grade 9 (Gold)")


@pytest.mark.asyncio
async def test_an_audit_row_is_written_only_when_something_changed(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    await _promote(client, [_item(student)])
    await _promote(client, [_item(student)])  # already in the active year -> skipped, nothing written

    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_promotion", AuditLog.entity_id == str(year.id)))).all()
    assert len(rows) == 1
    assert rows[0].user_id == ctx["coordinator"].id
    assert rows[0].metadata_json == {"academic_year_id": str(year.id), "promoted": 1, "held_back": 0, "failed": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_the_parent_view_shows_the_new_grade_immediately(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    assert (await _promote(client, [_item(student)])).status_code == 200

    await _login(client, ctx["parent"].email)
    listing = await client.get("/api/v1/school/students")
    assert listing.status_code == 200, listing.text
    assert [(s["grade_level"], s["grade_or_class"]) for s in listing.json()] == [(9, "Grade 9-A")]
    detail = await client.get(f"/api/v1/school/students/{student.id}")
    assert (detail.json()["grade_level"], detail.json()["grade_or_class"]) == (9, "Grade 9-A")


@pytest.mark.asyncio
async def test_the_dashboard_grade_counts_follow_the_promotion(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    await _login(client, ctx["coordinator"].email)

    def _counts(response):
        return {k["key"]: k["value"] for k in response.json()["school_crm_kpis"]}

    before = _counts(await client.get("/api/v1/school/dashboard"))
    assert (before["grade_8"], before["grade_9"]) == (2, 0)
    await _promote(client, [_item(ctx["students"][0])])
    after = _counts(await client.get("/api/v1/school/dashboard"))
    assert (after["grade_8"], after["grade_9"]) == (1, 1)


# ---------------------------------------------------------------- endpoint: authorization and validation


@pytest.mark.asyncio
async def test_a_coordinator_cannot_promote_students_at_another_school(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    foreign = school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(foreign)])

    assert response.status_code == 403
    await db_session.refresh(foreign)
    assert (foreign.grade_level, foreign.grade_or_class, foreign.academic_year_id) == (8, "Grade 8-A", None)
    assert await _history(db_session, foreign) == []


@pytest.mark.asyncio
async def test_one_foreign_student_in_a_mixed_list_rejects_the_whole_request(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    own, foreign = school_b["students"][0], school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(own), _item(foreign)])

    assert response.status_code == 403
    await db_session.refresh(own)
    assert (own.grade_level, own.academic_year_id) == (8, None)
    assert await _history(db_session, own) == []


@pytest.mark.asyncio
async def test_an_unknown_student_id_is_indistinguishable_from_a_foreign_one(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    await _login(client, school_b["coordinator"].email)

    foreign = await _promote(client, [_item(school_a["students"][0])])
    unknown = await client.post(URL, json={"items": [{"student_id": str(uuid.uuid4()), "action": "promote"}]})

    assert foreign.status_code == unknown.status_code == 403
    assert foreign.json() == unknown.json()


@pytest.mark.asyncio
async def test_a_rejected_request_never_locks_or_waits_on_another_schools_rows(client, db_session, future_years, monkeypatch):
    """Security (spec §14): the school filter is part of the locking query. If the request first locked every
    listed row and only then checked ownership, naming school A's IDs would make school B's coordinator wait
    on (and briefly hold) school A's rows -- a lock-griefing lever. Here school A's row is locked by someone
    else; B's request must be refused at once (403), not time out on the lock (409)."""
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    foreign = school_a["students"][0]
    await _login(client, school_b["coordinator"].email)
    monkeypatch.setattr("app.api.schools.PROMOTION_LOCK_TIMEOUT", "200ms")
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == foreign.id).with_for_update())
    try:
        response = await _promote(client, [_item(foreign)])
    finally:
        await db_session.rollback()

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_a_cross_school_attempt_is_audited_as_denied_with_counts_only(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    own, foreign = school_b["students"][0], school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(own), _item(foreign)])

    assert response.status_code == 403
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_promotion_denied", AuditLog.entity_id == str(school_b["school"].id)))).all()
    assert len(rows) == 1
    assert (rows[0].user_id, rows[0].entity_type, rows[0].outcome) == (school_b["coordinator"].id, "school", "denied")
    assert rows[0].metadata_json == {"requested": 2, "not_in_school": 1}  # counts only: no student IDs or names
    await db_session.refresh(own)
    assert own.grade_level == 8 and await _history(db_session, own) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role_key", ["principal", "teacher", "parent", "admin"])
async def test_only_a_school_coordinator_may_promote(client, db_session, future_years, role_key):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx[role_key].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 403
    await db_session.refresh(student)
    assert (student.grade_level, student.academic_year_id) == (8, None)


@pytest.mark.asyncio
async def test_an_unauthenticated_request_is_401(client, db_session):
    ctx = await _school(db_session)
    response = await _promote(client, [_item(ctx["students"][0])])
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_non_coordinator_with_a_malformed_body_gets_403_not_422(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent"].email)
    response = await client.post(URL, json={"items": "nope"})
    assert response.status_code == 403


INVALID_PAYLOADS = {
    "missing_items": lambda sid: {},
    "empty_items": lambda sid: {"items": []},
    "over_the_cap": lambda sid: {"items": [{"student_id": str(uuid.uuid4()), "action": "promote"} for _ in range(501)]},
    "duplicate_id": lambda sid: {"items": [{"student_id": sid, "action": "promote"}] * 2},
    "not_a_uuid": lambda sid: {"items": [{"student_id": "not-a-uuid", "action": "promote"}]},
    "unknown_action": lambda sid: {"items": [{"student_id": sid, "action": "graduate"}]},
    "hold_back_with_label": lambda sid: {"items": [{"student_id": sid, "action": "hold_back", "grade_or_class": "Grade 9"}]},
    "blank_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "   "}]},
    "label_too_long": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "x" * 61}]},
    # Security (spec §14): a NUL byte would otherwise reach PostgreSQL and surface as a 500; a client-supplied
    # school or year is refused loudly, not ignored.
    "nul_in_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "Grade\u0000 9"}]},
    "newline_in_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "Grade\n9"}]},
    "client_supplied_school_id": lambda sid: {"items": [{"student_id": sid, "action": "promote"}], "school_id": str(uuid.uuid4())},
    "client_supplied_year_on_item": lambda sid: {"items": [{"student_id": sid, "action": "promote", "academic_year_id": str(uuid.uuid4())}]},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(INVALID_PAYLOADS))
async def test_invalid_payloads_are_422_and_write_nothing(client, db_session, future_years, case):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await client.post(URL, json=INVALID_PAYLOADS[case](str(student.id)))

    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)
    await db_session.refresh(student)
    assert (student.grade_level, student.academic_year_id) == (8, None)


@pytest.mark.asyncio
async def test_no_active_academic_year_is_409(client, db_session, monkeypatch):
    async def _no_active_year(db):
        return None

    monkeypatch.setattr("app.api.schools._current_academic_year_id", _no_active_year)
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 409
    assert "active academic year" in response.json()["detail"]
    await db_session.refresh(student)
    assert student.grade_level == 8


# ---------------------------------------------------------------- endpoint: per-row outcomes


@pytest.mark.asyncio
async def test_a_top_grade_student_fails_alone_and_the_rest_commit(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 12", 12), ("Grade 8-A", 8)))
    top, other = ctx["students"]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(top), _item(other)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"promoted": 1, "held_back": 0, "failed": 1, "skipped": 0}
    assert (body["results"][0]["status"], body["results"][0]["reason"]) == ("failed", "terminal_grade")
    assert body["results"][0]["message"]
    await db_session.refresh(top)
    await db_session.refresh(other)
    assert (top.grade_level, top.academic_year_id) == (12, None)
    assert await _history(db_session, top) == []
    assert (other.grade_level, other.grade_or_class) == (9, "Grade 9-A")


@pytest.mark.asyncio
async def test_a_student_without_a_grade_level_fails_with_grade_level_not_set(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8", None),))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(ctx["students"][0])])

    assert response.status_code == 200, response.text
    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("failed", "grade_level_not_set")


@pytest.mark.asyncio
async def test_an_unswappable_label_fails_then_succeeds_with_an_override(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("8A", 8),))
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first = await _promote(client, [_item(student)])
    assert (first.json()["results"][0]["status"], first.json()["results"][0]["reason"]) == ("failed", "label_unparseable")
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (8, "8A")

    second = await _promote(client, [_item(student, grade_or_class="Grade 9A")])
    assert second.json()["results"][0]["status"] == "promoted"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (9, "Grade 9A")


@pytest.mark.asyncio
async def test_a_label_that_disagrees_with_grade_level_fails(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8-A", 9),))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(ctx["students"][0])])

    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("failed", "label_unparseable")
    assert "does not match" in response.json()["results"][0]["message"]


@pytest.mark.asyncio
async def test_a_swapped_label_over_60_characters_fails_only_its_own_row(client, db_session, future_years):
    await future_years()
    long_label = "Grade 9 " + "x" * 52  # 60 characters; "9" -> "10" would make it 61
    ctx = await _school(db_session, students=((long_label, 9), ("Grade 8-A", 8)))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(s) for s in ctx["students"]])

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert (results[0]["status"], results[0]["reason"]) == ("failed", "label_unparseable")
    assert "60 characters" in results[0]["message"]
    assert results[1]["status"] == "promoted"


@pytest.mark.asyncio
async def test_repeating_a_request_never_promotes_twice(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first = await _promote(client, [_item(student)])
    second = await _promote(client, [_item(student)])

    assert first.json()["results"][0]["status"] == "promoted"
    assert (second.json()["results"][0]["status"], second.json()["results"][0]["reason"]) == ("skipped", "already_in_active_year")
    assert (second.json()["results"][0]["grade_level"], second.json()["results"][0]["grade_or_class"]) == (9, "Grade 9-A")
    await db_session.refresh(student)
    assert student.grade_level == 9
    assert len(await _history(db_session, student)) == 1


@pytest.mark.asyncio
async def test_a_student_created_in_the_active_year_is_skipped(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    student.academic_year_id = year.id
    await db_session.commit()
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("skipped", "already_in_active_year")
    assert await _history(db_session, student) == []


# ---------------------------------------------------------------- concurrency


@pytest.mark.asyncio
async def test_two_concurrent_identical_requests_promote_each_student_once(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first, second = await asyncio.gather(_promote(client, [_item(student)]), _promote(client, [_item(student)]))

    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert sorted(r.json()["results"][0]["status"] for r in (first, second)) == ["promoted", "skipped"]
    await db_session.refresh(student)
    assert student.grade_level == 9
    assert len(await _history(db_session, student)) == 1


@pytest.mark.asyncio
async def test_a_request_that_cannot_get_the_row_locks_in_time_returns_409(client, db_session, future_years, monkeypatch):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    monkeypatch.setattr("app.api.schools.PROMOTION_LOCK_TIMEOUT", "200ms")
    # Hold the row lock in the test's own session, exactly as a slower concurrent promotion would.
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == student.id).with_for_update())
    try:
        response = await _promote(client, [_item(student)])
    finally:
        await db_session.rollback()

    assert response.status_code == 409
    assert "in progress" in response.json()["detail"]
    await db_session.refresh(student)
    assert student.grade_level == 8


@pytest.mark.asyncio
async def test_a_lock_timeout_is_logged_as_a_warning(client, db_session, future_years, monkeypatch, caplog):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    monkeypatch.setattr("app.api.schools.PROMOTION_LOCK_TIMEOUT", "200ms")
    caplog.set_level(logging.INFO, logger="app.school")
    coordinator_id, school_id = str(ctx["coordinator"].id), str(ctx["school"].id)  # read before the rollback below expires the ORM objects
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == student.id).with_for_update())
    try:
        await _promote(client, [_item(student)])
    finally:
        await db_session.rollback()

    assert _events(caplog, "student_promotion_lock_timeout") == [{"actor_id": coordinator_id, "school_id": school_id, "requested": 1, "lock_timeout": "200ms"}]
    assert [r.levelno for r in caplog.records if r.getMessage() == "student_promotion_lock_timeout"] == [logging.WARNING]


# ---------------------------------------------------------------- operational logging
# Structured events (app.core.logging convention): snake_case name, IDs and counts in `extra_fields`, never a
# student name, label or student ID -- the same rule as the audit metadata (spec §14).


def _events(caplog, name: str) -> list[dict]:
    return [r.extra_fields for r in caplog.records if r.name == "app.school" and r.getMessage() == name]


@pytest.mark.asyncio
async def test_a_completed_promotion_is_logged_with_ids_and_counts_only(client, db_session, future_years, caplog):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    caplog.set_level(logging.INFO, logger="app.school")

    await _promote(client, [_item(student, grade_or_class="Grade 9 (Gold)")])

    events = _events(caplog, "student_promotion_completed")
    assert events == [
        {"actor_id": str(ctx["coordinator"].id), "school_id": str(ctx["school"].id), "academic_year_id": str(year.id), "requested": 1, "promoted": 1, "held_back": 0, "failed": 0, "skipped": 0, "committed": True}
    ]
    dumped = json.dumps(events)
    assert "Gold" not in dumped and student.full_name not in dumped and str(student.id) not in dumped


@pytest.mark.asyncio
async def test_a_denied_cross_school_attempt_is_logged_as_a_warning(client, db_session, future_years, caplog):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    await _login(client, school_b["coordinator"].email)
    caplog.set_level(logging.INFO, logger="app.school")

    await _promote(client, [_item(school_a["students"][0])])

    assert _events(caplog, "student_promotion_denied") == [{"actor_id": str(school_b["coordinator"].id), "school_id": str(school_b["school"].id), "requested": 1, "not_in_school": 1}]
    assert [r.levelno for r in caplog.records if r.getMessage() == "student_promotion_denied"] == [logging.WARNING]


@pytest.mark.asyncio
async def test_promoting_with_no_active_year_is_logged(client, db_session, monkeypatch, caplog):
    async def _no_active_year(db):
        return None

    monkeypatch.setattr("app.api.schools._current_academic_year_id", _no_active_year)
    ctx = await _school(db_session)
    await _login(client, ctx["coordinator"].email)
    caplog.set_level(logging.INFO, logger="app.school")

    await _promote(client, [_item(ctx["students"][0])])

    assert _events(caplog, "student_promotion_no_active_year") == [{"actor_id": str(ctx["coordinator"].id), "school_id": str(ctx["school"].id)}]
