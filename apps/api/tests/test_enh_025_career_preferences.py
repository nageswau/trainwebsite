"""ENH-025 -- Career Counsellor career-preferences route (spec §3.4, §3.5, AC9)."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, SchoolStudent
from enh005_helpers import login, mk_school, mk_staff

URL = "/api/v1/school/students/{sid}/career-preferences"


@pytest_asyncio.fixture
async def world(db_session):
    w = await mk_school(db_session, label="C", students=1)
    w["counselor"] = await mk_staff(db_session, w["school"], w["admin"], role="career_counselor")
    return w


@pytest.mark.asyncio
async def test_counselor_reads_and_writes_the_four_fields(client, world, db_session):
    sid = world["students"][0].id
    await login(client, world["counselor"].email)
    assert (await client.get(URL.format(sid=sid))).json() == {"student_id": str(sid), "career_interests": None, "global_education_interest": None, "preferred_countries": None, "preferred_courses": None}
    r = await client.patch(URL.format(sid=sid), json={"career_interests": ["Design"], "global_education_interest": True})
    assert r.status_code == 200 and r.json()["career_interests"] == ["Design"]
    fresh = await db_session.get(SchoolStudent, sid, populate_existing=True)
    assert fresh.global_education_interest is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.student_career_preferences_update", AuditLog.entity_id == str(sid)))
    assert audit.metadata_json["changed_fields"] == ["career_interests", "global_education_interest"]
    assert "Design" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_invalid_value_is_422_naming_the_field(client, world):
    await login(client, world["counselor"].email)
    r = await client.patch(URL.format(sid=world["students"][0].id), json={"preferred_countries": "Japan"})
    assert r.status_code == 422 and r.json()["detail"] == "preferred_countries must be a list of text values"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["roll_number", "student_mobile", "school_id", "academic_year_id", "photo_key", "section"])
async def test_non_career_keys_are_422(client, world, key):
    await login(client, world["counselor"].email)
    r = await client.patch(URL.format(sid=world["students"][0].id), json={key: "x"})
    assert r.status_code == 422 and r.json()["detail"] == f"{key} is not an accepted field"


@pytest.mark.asyncio
async def test_counselor_outside_portfolio_is_403(client, world, db_session):
    other = await mk_school(db_session, label="CO", students=1)
    await login(client, world["counselor"].email)
    assert (await client.get(URL.format(sid=other["students"][0].id))).status_code == 403
    assert (await client.patch(URL.format(sid=other["students"][0].id), json={"career_interests": ["X"]})).status_code == 403


@pytest.mark.asyncio
async def test_other_roles_are_403(client, world):
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        assert (await client.get(URL.format(sid=world["students"][0].id))).status_code == 403, role
        assert (await client.patch(URL.format(sid=world["students"][0].id), json={"career_interests": ["X"]})).status_code == 403, role


@pytest.mark.asyncio
async def test_coordinator_sees_counselor_edits(client, world):
    sid = world["students"][0].id
    await login(client, world["counselor"].email)
    await client.patch(URL.format(sid=sid), json={"preferred_countries": ["Japan"]})
    await login(client, world["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{sid}")).json()["preferred_countries"] == ["Japan"]
