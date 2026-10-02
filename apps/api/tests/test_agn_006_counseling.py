"""AGN-006 -- an agency student's counseling record (spec §5; DEC-SCOPE-048 C1-C6; AC01-AC08, AC12)."""

import asyncio
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentOrg, AgentStudent, AgentStudentCounseling, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn004_helpers import RECORDS, mk_record, mk_staff

FULL = {
    "counseling_completed": True,
    "career_interest": "Data science",
    "course_preference": "MSc Data Science",
    "country_preference": "Ireland",
    "budget_amount": 2500000,
    "budget_currency": "INR",
    "remarks": "Needs scholarship options.\nPrefers the September intake.",
}
COUNSELING_KEYS = {
    "counseling_completed", "completed_at", "completed_by", "career_interest", "course_preference", "country_preference",
    "budget_amount", "budget_currency", "remarks", "updated_at", "updated_by",
}


def url(sid) -> str:
    return f"{RECORDS}/{sid}/counseling"


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling Agency {uniq()}")
    other = await mk_active_org(db_session, name=f"Counseling Other {uniq()}")
    s1 = await mk_staff(db_session, ctx["org"], full_name="Couns One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="Couns Two")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Asha Rao", assigned_member=s1["member"])
    unassigned = await mk_record(db_session, agent=ctx["master"], full_name="Nobody Assigned")
    archived = await mk_record(db_session, agent=ctx["master"], full_name="Archived Student", assigned_member=s1["member"], status="archived")
    account = await mk_user(db_session, role="overseas_student", full_name="Linked Student")
    linked = AgentStudent(agent_id=ctx["master"].id, student_id=account.id, status="active", assigned_member_id=s1["member"].id)
    db_session.add(linked)
    await db_session.commit()
    return ctx | {"other": other, "s1": s1, "s2": s2, "row": row, "unassigned": unassigned, "archived": archived, "linked": linked}


async def _records(db, sid) -> list[AgentStudentCounseling]:
    stmt = select(AgentStudentCounseling).where(AgentStudentCounseling.agent_student_id == sid).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def _audits(db, sid) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == "agent_student.counseling", AuditLog.entity_id == str(sid)))).all())


@pytest.mark.asyncio
async def test_master_saves_and_reads_back_every_field(agency):  # AC01
    async with client_for(agency["master"].email) as c:
        saved = await c.put(url(agency["row"].id), json=FULL)
        read = await c.get(f"{RECORDS}/{agency['row'].id}")
    assert saved.status_code == 200, saved.text
    counseling = read.json()["student"]["counseling"]
    assert saved.json()["student"]["counseling"] == counseling
    assert {k: counseling[k] for k in FULL} == {**FULL, "budget_amount": "2500000.00"}
    assert counseling["completed_at"] and counseling["completed_by"] == agency["master"].full_name
    assert counseling["updated_by"] == agency["master"].full_name


@pytest.mark.asyncio
async def test_assigned_staff_can_save(db_session, agency):  # AC02
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.put(url(agency["row"].id), json={"counseling_completed": False, "career_interest": "Law"})
    assert response.status_code == 200, response.text
    [record] = await _records(db_session, agency["row"].id)
    assert record.career_interest == "Law" and record.updated_by_user_id == agency["s1"]["user"].id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caller", "target"),
    [("s2", "row"), ("s1", "unassigned"), ("other", "row"), ("master", "unknown")],
    ids=["other-staff", "unassigned-to-caller", "other-agency", "unknown-id"],
)
async def test_out_of_scope_is_404_and_writes_nothing(db_session, agency, caller, target):  # AC02, AC12; Review Focus 3
    email = {"s2": agency["s2"]["user"].email, "s1": agency["s1"]["user"].email, "other": agency["other"]["master"].email, "master": agency["master"].email}[caller]
    sid = uuid.uuid4() if target == "unknown" else agency[target].id
    async with client_for(email) as c:
        response = await c.put(url(sid), json=FULL)
    assert response.status_code == 404 and response.json()["detail"] == "Student not found"
    assert await _records(db_session, sid) == [] and await _audits(db_session, sid) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {**FULL, "budget_amount": -1},
        {**FULL, "budget_amount": "-0.01"},
        {**FULL, "budget_amount": 100000000},
        {**FULL, "budget_amount": "10.123"},
        {**FULL, "budget_amount": "NaN"},
        {**FULL, "budget_currency": "JPY"},
        {**FULL, "budget_amount": None, "budget_currency": "USD"},
        {**FULL, "completed_by": "someone"},
        {k: v for k, v in FULL.items() if k != "counseling_completed"},
        {**FULL, "career_interest": "x" * 201},
        {**FULL, "remarks": "x" * 2001},
        {**FULL, "remarks": "bad\x00byte"},
    ],
    ids=["negative", "negative-cents", "over-max", "three-decimals", "nan", "unknown-currency", "currency-alone", "server-owned", "missing-completed", "career-long", "remarks-long", "nul"],
)
async def test_invalid_body_is_422_and_writes_nothing(db_session, agency, body):  # AC03; Review Focus 5
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency["row"].id), json=body)
    assert response.status_code == 422
    assert await _records(db_session, agency["row"].id) == []


@pytest.mark.asyncio
async def test_amount_alone_is_inr_and_a_numeric_string_is_accepted(agency):  # AC03, AC12
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency["row"].id), json={"counseling_completed": False, "budget_amount": "1500.5"})
    assert response.status_code == 200, response.text
    counseling = response.json()["student"]["counseling"]
    assert (counseling["budget_amount"], counseling["budget_currency"]) == ("1500.50", "INR")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "detail"),
    [("linked", "Counseling is recorded only for students without a login"), ("archived", "Unarchive this student first")],
)
async def test_login_or_archived_student_is_409(db_session, agency, target, detail):  # AC04
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency[target].id), json=FULL)
    assert response.status_code == 409 and response.json()["detail"] == detail
    assert await _records(db_session, agency[target].id) == []


@pytest.mark.asyncio
async def test_completed_stamp_is_set_kept_and_cleared(db_session, agency):  # AC05
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        first = (await c.put(url(sid), json=FULL)).json()["student"]["counseling"]
    async with client_for(agency["s1"]["user"].email) as c:
        kept = (await c.put(url(sid), json={**FULL, "remarks": "Staff follow-up"})).json()["student"]["counseling"]
        cleared = (await c.put(url(sid), json={**FULL, "counseling_completed": False})).json()["student"]["counseling"]
    assert first["completed_at"] and first["completed_by"] == agency["master"].full_name
    assert kept["completed_at"] == first["completed_at"] and kept["completed_by"] == agency["master"].full_name  # yes -> yes keeps
    assert kept["updated_by"] == "Couns One"
    assert cleared["completed_at"] is None and cleared["completed_by"] is None
    [record] = await _records(db_session, sid)
    assert record.completed_by_user_id is None


@pytest.mark.asyncio
async def test_audit_names_changed_fields_only_and_repeat_saves_write_none(db_session, agency):  # AC06; Review Focus 2
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        assert (await c.put(url(sid), json=FULL)).status_code == 200
        assert (await c.put(url(sid), json=FULL)).status_code == 200  # identical: no-op
        same = {**FULL, "budget_amount": "2500000.00", "career_interest": "  Data science  "}  # equal after normalisation
        assert (await c.put(url(sid), json=same)).status_code == 200
        assert (await c.put(url(sid), json={**FULL, "remarks": "Changed remark 4417"})).status_code == 200
    audits = await _audits(db_session, sid)
    assert sorted((a.metadata_json for a in audits), key=lambda m: -len(m["fields"])) == [{"fields": sorted(FULL)}, {"fields": ["remarks"]}]
    blob = json.dumps([a.metadata_json for a in audits])
    assert "2500000" not in blob and "scholarship" not in blob and "4417" not in blob


@pytest.mark.asyncio
async def test_a_first_save_of_just_no_creates_the_record(db_session, agency):  # AC06, AC08
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(sid), json={"counseling_completed": False})
    assert response.status_code == 200, response.text
    counseling = response.json()["student"]["counseling"]
    assert counseling["counseling_completed"] is False and counseling["career_interest"] is None
    [audit] = await _audits(db_session, sid)
    assert audit.metadata_json == {"fields": ["counseling_completed"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["student", "super_admin", "suspended"])
async def test_non_agents_and_suspended_agencies_are_403(db_session, agency, who):  # AC07
    if who == "suspended":
        org = await db_session.get(AgentOrg, agency["org"].id, populate_existing=True)
        org.status = "suspended"
        await db_session.commit()
        email = agency["master"].email
    else:
        user = await mk_user(db_session, role="overseas_student" if who == "student" else "super_admin", division="overseas" if who == "student" else "global")
        email = user.email
    async with client_for(email) as c:
        response = await c.put(url(agency["row"].id), json=FULL)
    assert response.status_code == 403
    assert await _records(db_session, agency["row"].id) == []


@pytest.mark.asyncio
async def test_put_replaces_the_record_and_other_contracts_are_unchanged(agency):  # AC08
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        before = (await c.get(f"{RECORDS}/{sid}")).json()["student"]
        await c.put(url(sid), json=FULL)
        replaced = (await c.put(url(sid), json={"counseling_completed": True})).json()["student"]["counseling"]
        listed = (await c.get(RECORDS, params={"q": "Asha Rao"})).json()["items"]
        patched = await c.patch(f"{RECORDS}/{sid}", json={"preferred_country": "Canada"})
    assert before["counseling"] is None
    assert replaced["counseling_completed"] is True
    assert (replaced["career_interest"], replaced["budget_amount"], replaced["budget_currency"], replaced["remarks"]) == (None, None, None, None)
    assert listed and all("counseling" not in item for item in listed)
    assert patched.status_code == 200
    body = patched.json()["student"]
    assert body["preferred_country"] == "Canada" and body["counseling"]["counseling_completed"] is True  # C3: separate fields


@pytest.mark.asyncio
async def test_the_record_exposes_no_ids(db_session, agency):  # AC12
    async with client_for(agency["master"].email) as c:
        counseling = (await c.put(url(agency["row"].id), json=FULL)).json()["student"]["counseling"]
    assert set(counseling) == COUNSELING_KEYS
    [record] = await _records(db_session, agency["row"].id)
    text = json.dumps(counseling)
    for value in (record.id, record.updated_by_user_id, record.completed_by_user_id):
        assert str(value) not in text


@pytest.mark.asyncio
async def test_two_first_saves_at_once_leave_one_record(db_session, agency):  # Review Focus 4
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c1, client_for(agency["s1"]["user"].email) as c2:
        results = await asyncio.gather(c1.put(url(sid), json=FULL), c2.put(url(sid), json={**FULL, "remarks": "Other"}))
    assert [r.status_code for r in results] == [200, 200]
    assert len(await _records(db_session, sid)) == 1
