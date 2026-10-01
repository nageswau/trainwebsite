"""ENH-020 -- funding support case reads (spec §4 E3/E4, D5, D12, D13; AC11, AC17, AC18; plan Review Focus 4)."""

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff, mk_student, move_student_directly
from sqlalchemy import select, update

from app.models import AuditLog, School, SchoolFundingRecord, SchoolParentLink

CASES = "/api/v1/school/funding-records"
MINE = "/api/v1/school/career-counselor/funding-records"
TEACHERS_DENIED = "Funding support cases are not visible to teachers."


def _student_cases(student_id) -> str:
    return f"/api/v1/school/students/{student_id}/funding-records"


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E20R", students=2)
    ctx["counselor"] = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    ctx["sid"] = str(ctx["students"][0].id)
    return ctx


async def _open(client, world, student_id=None, support_type="education_loan", **body) -> dict:
    await login(client, world["counselor"].email)
    r = await client.post(CASES, json={"school_student_id": student_id or world["sid"], "support_type": support_type, **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _denied(db, user_id, reason):
    return await db.scalar(select(AuditLog).where(AuditLog.action == "school.funding_record_denied", AuditLog.user_id == user_id, AuditLog.metadata_json["reason"].as_string() == reason))


@pytest.mark.asyncio
async def test_counsellor_list_shows_open_cases_first_then_most_recent(client, world, db_session):  # E3
    first = await _open(client, world)
    second = await _open(client, world, support_type="scholarship")
    third = await _open(client, world, str(world["students"][1].id), "funding_guidance")
    r = await client.patch(f"{CASES}/{first['id']}", json={"status": "closed", "closure_reason": "Withdrawn"})
    assert r.status_code == 200
    listed = [c["id"] for c in (await client.get(MINE)).json()]
    assert listed[-1] == first["id"]
    assert set(listed[:2]) == {second["id"], third["id"]}


@pytest.mark.asyncio
async def test_counsellor_list_covers_only_the_portfolio(client, world, db_session):  # E3
    mine = await _open(client, world)
    other = await mk_school(db_session, label="E20R-Other", students=1)
    other_counselor = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    await login(client, other_counselor.email)
    assert (await client.post(CASES, json={"school_student_id": str(other["students"][0].id), "support_type": "scholarship"})).status_code == 201
    await login(client, world["counselor"].email)
    assert [c["id"] for c in (await client.get(MINE)).json()] == [mine["id"]]
    await login(client, world["coordinator"].email)
    r = await client.get(MINE)
    assert (r.status_code, r.json()["detail"]) == (403, "Career Counselor role required")


@pytest.mark.parametrize("who", ["coordinator", "principal", "parent", "counselor"])
@pytest.mark.asyncio
async def test_readers_in_scope_see_the_cases(client, world, who):  # AC11
    case = await _open(client, world, provider_name="HDFC", notes="n")
    await login(client, world[who].email)
    r = await client.get(_student_cases(world["sid"]))
    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()] == [case["id"]]
    assert r.json()[0]["provider_name"] == "HDFC"


@pytest.mark.asyncio
async def test_an_assigned_teacher_is_refused_and_audited(client, world, db_session):  # AC11, AC18, D5
    await _open(client, world)
    await login(client, world["teacher"].email)  # the first student IS assigned to this teacher
    r = await client.get(_student_cases(world["sid"]))
    assert (r.status_code, r.json()["detail"]) == (403, TEACHERS_DENIED)
    row = await _denied(db_session, world["teacher"].id, "teacher")
    assert (row.entity_type, row.entity_id) == ("school_student", world["sid"])


@pytest.mark.asyncio
async def test_out_of_scope_readers_are_refused_and_audited(client, world, db_session):  # AC11, AC18
    await _open(client, world)
    other = await mk_school(db_session, label="E20R-Out", students=1)
    academic = await mk_staff(db_session, world["school"], world["admin"], role="academic_team")
    outsider_counselor = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    cases = [(other["coordinator"], "scope"), (other["principal"], "scope"), (other["parent"], "scope"), (outsider_counselor, "scope"), (academic, "role")]
    for user, reason in cases:
        await login(client, user.email)
        r = await client.get(_student_cases(world["sid"]))
        assert r.status_code == 403, (user.role, r.text)
        assert await _denied(db_session, user.id, reason) is not None, user.role
    await login(client, world["coordinator"].email)
    assert (await client.get(_student_cases("00000000-0000-0000-0000-000000000000"))).status_code == 404


@pytest.mark.asyncio
async def test_a_parent_of_children_at_two_schools_sees_each_child_only(client, world, db_session):  # Review Focus 4
    other = await mk_school(db_session, label="E20R-Second", admin=world["admin"], students=0)
    second_child = await mk_student(db_session, other["school"], other["coordinator"], "Sibling")
    db_session.add(SchoolParentLink(parent_user_id=world["parent"].id, school_student_id=second_child.id, linked_by_user_id=other["coordinator"].id))
    await db_session.commit()
    other_counselor = await mk_staff(db_session, other["school"], world["admin"], role="career_counselor")
    first_case = await _open(client, world)
    await login(client, other_counselor.email)
    r = await client.post(CASES, json={"school_student_id": str(second_child.id), "support_type": "scholarship"})
    assert r.status_code == 201
    await login(client, world["parent"].email)
    assert [c["id"] for c in (await client.get(_student_cases(world["sid"]))).json()] == [first_case["id"]]
    assert [c["support_type"] for c in (await client.get(_student_cases(second_child.id))).json()] == ["scholarship"]
    assert (await client.get(_student_cases(world["students"][1].id))).status_code == 403  # not their child


@pytest.mark.asyncio
async def test_a_transfer_hides_the_previous_schools_cases_from_staff_only(client, world, db_session):  # AC17, D12
    old_case = await _open(client, world)
    new = await mk_school(db_session, label="E20R-New", admin=world["admin"], students=0)
    new_counselor = await mk_staff(db_session, new["school"], world["admin"], role="career_counselor")
    await move_student_directly(db_session, world["students"][0], new["school"])
    await login(client, new["coordinator"].email)
    assert (await client.get(_student_cases(world["sid"]))).json() == []
    await login(client, new_counselor.email)
    assert (await client.get(MINE)).json() == []
    assert (await client.get(_student_cases(world["sid"]))).json() == []
    r = await client.post(CASES, json={"school_student_id": world["sid"], "support_type": "education_loan"})
    assert r.status_code == 201  # the new school starts its own case of the same type
    await login(client, world["counselor"].email)  # the old school's counsellor no longer has the student at all
    assert old_case["id"] not in [c["id"] for c in (await client.get(MINE)).json()]
    await login(client, world["parent"].email)
    assert {c["id"] for c in (await client.get(_student_cases(world["sid"]))).json()} == {old_case["id"], r.json()["id"]}


@pytest.mark.asyncio
async def test_reads_are_not_tier_gated(client, world, db_session):  # spec §4
    case = await _open(client, world)
    await db_session.execute(update(School).where(School.id == world["school"].id).values(tier=None))
    await db_session.commit()
    for who in ("counselor", "coordinator", "parent"):
        await login(client, world[who].email)
        assert [c["id"] for c in (await client.get(_student_cases(world["sid"]))).json()] == [case["id"]], who
    await login(client, world["counselor"].email)
    assert [c["id"] for c in (await client.get(MINE)).json()] == [case["id"]]


@pytest.mark.asyncio
async def test_responses_carry_no_school_id_or_student_master_data(client, world, db_session):
    await _open(client, world)
    await login(client, world["coordinator"].email)
    body = (await client.get(_student_cases(world["sid"]))).json()[0]
    assert "school_id" not in body and "full_name" not in body and "date_of_birth" not in body
    assert await db_session.scalar(select(SchoolFundingRecord.school_id).where(SchoolFundingRecord.id == body["id"])) == world["school"].id
