"""ENH-025 -- Student Master fields on POST/PATCH/GET /school/students (spec §3.3, §3.6, AC1/2/5/7)."""

import asyncio
import uuid

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school
from httpx import ASGITransport
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, SchoolStudent

STUDENTS = "/api/v1/school/students"
FULL = {
    "section": "A", "roll_number": "7", "gender": "female", "student_mobile": "+91 98765 43210", "city": "Pune",
    "subjects": ["Maths", "Physics"], "career_interests": ["Engineering"], "global_education_interest": True,
    "preferred_countries": ["Germany"], "preferred_courses": ["Mechanical Engineering"],
}
LEGACY_KEYS = {"id", "student_code", "full_name", "date_of_birth", "grade_or_class", "assigned_teacher_user_id", "pending_parent_email", "academic_year_id", "grade_level"}


@pytest_asyncio.fixture
async def world(db_session):
    return await mk_school(db_session, label="F", students=1)


@pytest.mark.asyncio
async def test_create_sets_every_field_and_response_is_additive(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "Asha Rao", "grade_level": 8, **FULL})
    assert r.status_code == 201, r.text
    body = r.json()
    assert LEGACY_KEYS <= set(body)
    for key, value in FULL.items():
        assert body[key] == value, key
    assert body["has_photo"] is False
    assert "photo_key" not in body and "photo_content_type" not in body


@pytest.mark.asyncio
async def test_legacy_payload_behaves_as_before(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "Legacy Kid", "grade_or_class": "Grade 5", "grade_level": 5})
    assert r.status_code == 201
    body = r.json()
    assert body["grade_or_class"] == "Grade 5" and body["grade_level"] == 5
    assert all(body[key] is None for key in FULL)


@pytest.mark.asyncio
async def test_patch_absent_keeps_null_clears_and_value_changes(client, world):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    assert (await client.patch(f"{STUDENTS}/{sid}", json=FULL)).status_code == 200
    r = await client.patch(f"{STUDENTS}/{sid}", json={"city": None, "subjects": [], "gender": "male"})
    assert r.status_code == 200
    body = r.json()
    assert body["city"] is None and body["subjects"] is None and body["gender"] == "male"
    assert body["section"] == "A" and body["preferred_countries"] == ["Germany"]


@pytest.mark.asyncio
async def test_patch_ignores_system_keys(client, world, db_session):
    await login(client, world["coordinator"].email)
    student = world["students"][0]
    before_year = student.academic_year_id
    r = await client.patch(f"{STUDENTS}/{student.id}", json={"academic_year_id": str(uuid.uuid4()), "school_id": str(uuid.uuid4()), "photo_key": "x", "city": "Pune"})
    assert r.status_code == 200
    fresh = await db_session.get(SchoolStudent, student.id, populate_existing=True)
    assert fresh.academic_year_id == before_year and fresh.school_id == world["school"].id and fresh.photo_key is None and fresh.city == "Pune"


@pytest.mark.asyncio
async def test_invalid_field_is_422_naming_the_field(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "X", "gender": "robot"})
    assert r.status_code == 422
    assert r.json()["detail"] == "gender must be one of: female, male, other, prefer_not_to_say"


@pytest.mark.asyncio
async def test_roll_clash_is_409_case_insensitive_section(client, world):
    await login(client, world["coordinator"].email)
    base = {"grade_level": 8, "roll_number": "12"}
    assert (await client.post(STUDENTS, json={"full_name": "One", "section": "A", **base})).status_code == 201
    r = await client.post(STUDENTS, json={"full_name": "Two", "section": "a", **base})
    assert r.status_code == 409
    assert r.json()["detail"] == "roll_number '12' is already used in this grade and section for this academic year"


@pytest.mark.asyncio
async def test_blank_section_is_its_own_group(client, world):
    await login(client, world["coordinator"].email)
    assert (await client.post(STUDENTS, json={"full_name": "One", "grade_level": 5, "roll_number": "3"})).status_code == 201
    assert (await client.post(STUDENTS, json={"full_name": "Two", "grade_level": 5, "roll_number": "3"})).status_code == 409
    assert (await client.post(STUDENTS, json={"full_name": "Three", "grade_level": 5, "section": "B", "roll_number": "3"})).status_code == 201


@pytest.mark.asyncio
async def test_students_without_roll_numbers_are_unconstrained(client, world):
    await login(client, world["coordinator"].email)
    for name in ("A", "B"):
        assert (await client.post(STUDENTS, json={"full_name": name, "grade_level": 6, "section": "C"})).status_code == 201


@pytest.mark.asyncio
async def test_patch_into_a_taken_roll_is_409_and_nothing_changes(client, world, db_session):
    await login(client, world["coordinator"].email)
    # Both created through the API so they share the current academic year (a different year may reuse a roll).
    await client.post(STUDENTS, json={"full_name": "Holder", "grade_level": 8, "section": "A", "roll_number": "9"})
    sid = (await client.post(STUDENTS, json={"full_name": "Mover", "grade_level": 8})).json()["id"]
    r = await client.patch(f"{STUDENTS}/{sid}", json={"section": "A", "roll_number": "9", "city": "Goa"})
    assert r.status_code == 409
    fresh = await db_session.get(SchoolStudent, sid, populate_existing=True)
    assert fresh.roll_number is None and fresh.city is None


@pytest.mark.asyncio
async def test_concurrent_creates_with_the_same_roll_yield_one_success(world):
    async def attempt(name):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await login(c, world["coordinator"].email)
            return await c.post(STUDENTS, json={"full_name": name, "grade_level": 9, "section": "D", "roll_number": "1"})

    results = await asyncio.wait_for(asyncio.gather(attempt("P"), attempt("Q")), timeout=20)
    assert sorted(r.status_code for r in results) == [201, 409]


@pytest.mark.asyncio
async def test_other_roles_cannot_write(client, world):
    for role in ("teacher", "principal", "parent"):
        await login(client, world[role].email)
        assert (await client.patch(f"{STUDENTS}/{world['students'][0].id}", json={"city": "X"})).status_code == 403, role


@pytest.mark.asyncio
async def test_other_school_coordinator_cannot_write(client, db_session, world):
    other = await mk_school(db_session, label="O", students=0)
    await login(client, other["coordinator"].email)
    assert (await client.patch(f"{STUDENTS}/{world['students'][0].id}", json={"city": "X"})).status_code == 403


@pytest.mark.asyncio
async def test_readers_see_new_fields_within_scope(client, world):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    await client.patch(f"{STUDENTS}/{sid}", json={"city": "Pune"})
    for role in ("principal", "teacher", "parent"):
        await login(client, world[role].email)
        r = await client.get(f"{STUDENTS}/{sid}")
        assert r.status_code == 200 and r.json()["city"] == "Pune", role


@pytest.mark.asyncio
async def test_audit_records_field_names_not_values(client, world, db_session):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    await client.patch(f"{STUDENTS}/{sid}", json={"student_mobile": "+91 98765 43210", "city": "Pune"})
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.student_update", AuditLog.entity_id == str(sid)).order_by(AuditLog.created_at.desc()))
    assert row.metadata_json["changed_fields"] == ["city", "student_mobile"]
    assert "98765" not in str(row.metadata_json) and "Pune" not in str(row.metadata_json)
