"""ENH-025 -- bulk upload + template carry the new columns (spec §3.3, AC1/2/5/6)."""

import csv
import io
import uuid

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school
from sqlalchemy import select

from app.models import SchoolAccountInvite, SchoolStudent

UPLOAD = "/api/v1/school/students/bulk-upload"
ORIGINAL = ["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level"]
NEW = ["section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "global_education_interest", "preferred_countries", "preferred_courses"]


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


async def _upload(client, data: bytes):
    return await client.post(UPLOAD, files={"file": ("roster.csv", data, "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})


async def _students(db_session, school_id):
    return {s.full_name: s for s in (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.school_id == school_id))).all()}


@pytest_asyncio.fixture
async def world(db_session):
    return await mk_school(db_session, label="B", students=0)


@pytest.mark.asyncio
async def test_template_keeps_original_columns_first_then_new(client, world):
    await login(client, world["coordinator"].email)
    r = await client.get("/api/v1/school/students/roster-template")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ORIGINAL + NEW
    assert len(rows[1]) == len(ORIGINAL + NEW)


@pytest.mark.asyncio
async def test_all_new_columns_load(client, world, db_session):
    await login(client, world["coordinator"].email)
    data = _csv(ORIGINAL + NEW, [["Asha", "", "Grade 8-A", "", "", "", "8", "A", "7", "Female", "+91 98765 43210", "Pune", "Maths;Physics", "Engineering", "yes", "Germany;Canada", "Mechanical"]])
    r = await _upload(client, data)
    assert r.json()["accepted_count"] == 1, r.text
    s = (await _students(db_session, world["school"].id))["Asha"]
    assert (s.section, s.roll_number, s.gender, s.city, s.student_mobile) == ("A", "7", "female", "Pune", "+91 98765 43210")
    assert s.subjects == ["Maths", "Physics"] and s.preferred_countries == ["Germany", "Canada"] and s.preferred_courses == ["Mechanical"]
    assert s.career_interests == ["Engineering"] and s.global_education_interest is True


@pytest.mark.asyncio
async def test_original_seven_column_csv_still_works(client, world):
    await login(client, world["coordinator"].email)
    r = await _upload(client, _csv(ORIGINAL, [["Legacy", "2015-04-12", "Grade 5", "", "", "", "5"]]))
    assert r.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_short_rows_and_trailing_empty_column_mean_not_set(client, world, db_session):
    await login(client, world["coordinator"].email)
    raw = b"full_name,grade_level,section,city,\nShort,6\nTrail,6,B,,\n"
    r = await _upload(client, raw)
    assert r.json()["accepted_count"] == 2, r.text
    rows = await _students(db_session, world["school"].id)
    assert rows["Short"].section is None and rows["Trail"].section == "B" and rows["Trail"].city is None


@pytest.mark.asyncio
async def test_bad_values_reject_only_that_row_without_echoing_mobile(client, world):
    await login(client, world["coordinator"].email)
    data = _csv(["full_name", "gender", "student_mobile", "global_education_interest"], [
        ["Good", "male", "", ""], ["BadGender", "robot", "", ""], ["BadMobile", "", "12ab", ""], ["BadBool", "", "", "maybe"],
    ])
    body = (await _upload(client, data)).json()
    assert body["accepted_count"] == 1 and body["rejected_count"] == 3
    messages = {r["row_number"]: r["error_message"] for r in body["rows"] if r["status"] == "rejected"}
    assert messages[2] == "gender must be one of: female, male, other, prefer_not_to_say"
    assert messages[3].startswith("student_mobile ") and "12ab" not in messages[3]
    assert messages[4] == "global_education_interest must be yes or no"


@pytest.mark.asyncio
async def test_roll_clash_inside_the_file_rejects_the_later_row_only(client, world, db_session):
    await login(client, world["coordinator"].email)
    data = _csv(["full_name", "grade_level", "section", "roll_number"], [
        ["R1", "8", "A", "7"], ["R2", "8", "A", "8"], ["R3", "8", "B", "7"], ["R4", "8", "a", "7"], ["R5", "8", "A", "9"],
    ])
    body = (await _upload(client, data)).json()
    assert body["accepted_count"] == 4 and body["rejected_count"] == 1
    rejected = [r for r in body["rows"] if r["status"] == "rejected"]
    assert rejected[0]["row_number"] == 4
    assert rejected[0]["error_message"] == "roll_number '7' is already used in this grade and section for this academic year"
    assert set(await _students(db_session, world["school"].id)) == {"R1", "R2", "R3", "R5"}


@pytest.mark.asyncio
async def test_rejected_roll_row_never_invites_its_parent(client, world, db_session):
    await login(client, world["coordinator"].email)
    email = f"enh025-parent-{uuid.uuid4().hex[:6]}@example.local"
    data = _csv(["full_name", "grade_level", "section", "roll_number", "parent_email"], [["First", "8", "A", "1", ""], ["Second", "8", "A", "1", email]])
    body = (await _upload(client, data)).json()
    assert body["rejected_count"] == 1
    assert (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.pending_parent_email == email))).all() == []
    assert (await db_session.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.email == email))).all() == []
