"""ccrm-051 (DEC-SCOPE-327): the agent-Master commission per course -- an optional `agent_commission` on POST / PATCH
/partnership/universities/{id}/courses for super_admin / overseas_admin only (403 for anyone else, even null), audited with before/after.
The agent Master's partner-university detail shows each course's effective value: the course's, else the university's, with its source."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, OverseasCourse
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_staff
from tests.test_upc_017_courses import add_course, course_body, courses_url
from tests.upc001_helpers import as_role, login
from tests.upc003_helpers import BASE, catalogue_country, create
from tests.upc007_helpers import owned_university

PARTNERS = "/api/v1/workflows/overseas/agent/crm/partner-universities"
TWELVE = {"percent": "12", "note": "Course rate"}
REFUSED = "Only a super admin or an overseas admin can change the agent commission"


async def _audits(db, course_id) -> list[dict]:
    rows = await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(course_id), AuditLog.action == "university_course.agent_commission").order_by(AuditLog.created_at))
    return [{k: v for k, v in r.metadata_json.items() if k != "university_id"} for r in rows]


async def _published(client, db, **commission) -> dict:
    """A published university as overseas_admin (the client stays signed in as them)."""
    await as_role(client, db, "overseas_admin", "overseas")
    uni = await create(client, (await catalogue_country(db)).id, overview="An overview.", **commission)
    assert (await client.post(f"{BASE}/{uni['id']}/publish")).status_code == 200
    return uni


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_admin", "super_admin"])
async def test_an_admin_adds_a_course_with_its_agent_commission(client, db_session, role):
    await as_role(client, db_session, role, "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    course = await add_course(client, uni["id"], agent_commission=TWELVE)
    assert course["agent_commission"] == {"percent": "12.00", "amount": None, "currency": None, "note": "Course rate"}
    row = await db_session.get(OverseasCourse, uuid.UUID(course["id"]), populate_existing=True)
    assert row.agent_commission_percent == 12 and row.agent_commission_note == "Course rate"
    assert await _audits(db_session, course["id"]) == [{"before": None, "after": course["agent_commission"]}]
    created = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == course["id"], AuditLog.action == "university_course.create"))
    assert "agent_commission" not in created.metadata_json["fields"]
    plain = await add_course(client, uni["id"])
    assert plain["agent_commission"] is None and await _audits(db_session, plain["id"]) == []


@pytest.mark.asyncio
async def test_ac5_an_edit_sets_keeps_and_clears_with_an_audit_per_change(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    course = await add_course(client, uni["id"])
    url = courses_url(uni["id"], course["id"])
    r = await client.patch(url, json={"agent_commission": {"amount": "500", "currency": "GBP"}})
    assert r.status_code == 200, r.text
    after = {"percent": None, "amount": "500.00", "currency": "GBP", "note": None}
    assert r.json()["course"]["agent_commission"] == after
    assert (await client.patch(url, json={"agent_commission": {"amount": "500.00", "currency": "GBP"}})).status_code == 200  # unchanged
    assert (await client.patch(url, json={"duration": "2 years"})).json()["course"]["agent_commission"] == after  # omitted = kept
    cleared = await client.patch(url, json={"agent_commission": None})
    assert cleared.status_code == 200 and cleared.json()["course"]["agent_commission"] is None
    assert await _audits(db_session, course["id"]) == [{"before": None, "after": after}, {"before": after, "after": None}]


@pytest.mark.asyncio
async def test_the_rate_is_validated_like_the_university_one(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    for bad in ({"percent": "10", "amount": "100", "currency": "GBP"}, {"amount": "100"}, {"percent": "0"}, {"percent": "100.01"}, {"percent": "5", "x": 1}):
        r = await client.post(courses_url(uni["id"]), json=course_body(agent_commission=bad))
        assert r.status_code == 422, bad
        assert r.json()["detail"][0]["loc"][:2] == ["body", "agent_commission"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [TWELVE, None])
async def test_ac4_partnership_roles_sending_the_field_are_403_and_never_see_it(client, db_session, value):
    head, pm, uni = await owned_university(client, db_session)
    await as_role(client, db_session, "super_admin", "overseas")
    course = await add_course(client, uni["id"], agent_commission={"percent": "16.5"})
    for who in (pm, head):
        await login(client, who)
        r = await client.post(courses_url(uni["id"]), json=course_body(agent_commission=value))
        assert r.status_code == 403 and r.json()["detail"] == REFUSED
        r = await client.patch(courses_url(uni["id"], course["id"]), json={"duration": "3 years", "agent_commission": value})
        assert r.status_code == 403 and "16.50" not in r.text
        listed = await client.get(courses_url(uni["id"]))
        assert listed.status_code == 200 and "agent_commission" not in listed.text and "16.50" not in listed.text
    row = await db_session.get(OverseasCourse, uuid.UUID(course["id"]), populate_existing=True)
    assert row.agent_commission_percent == 16.5 and row.duration != "3 years"
    await login(client, pm)
    ok = await client.patch(courses_url(uni["id"], course["id"]), json={"duration": "3 years"})
    assert ok.status_code == 200 and "agent_commission" not in ok.text


@pytest.mark.asyncio
async def test_an_overseas_admin_outside_overseas_is_refused(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    await as_role(client, db_session, "overseas_admin", "it")
    r = await client.post(courses_url(uni["id"]), json=course_body(agent_commission=TWELVE))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ac1_ac2_the_master_sees_each_courses_effective_commission_with_its_source(client, db_session):
    uni = await _published(client, db_session, agent_commission={"percent": "10"})
    await add_course(client, uni["id"], title="MSc Own Rate", agent_commission=TWELVE)
    await add_course(client, uni["id"], title="MSc Fallback")
    org = await mk_active_org(db_session)
    staff = await mk_staff(db_session, org["org"])
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        courses = {c["title"]: c for c in (await master.get(f"{PARTNERS}/{uni['id']}")).json()["university"]["courses"]}
    assert courses["MSc Own Rate"]["agent_commission_effective"] == {"percent": "12.00", "amount": None, "currency": None, "note": "Course rate", "source": "course"}
    assert courses["MSc Fallback"]["agent_commission_effective"] == {"percent": "10.00", "amount": None, "currency": None, "note": None, "source": "university"}
    assert "agent_commission" not in courses["MSc Own Rate"]  # only the effective value, never the raw course column set
    async with client_for(staff["user"].email) as s:
        r = await s.get(f"{PARTNERS}/{uni['id']}")
        assert r.status_code == 200 and "agent_commission" not in r.text and "12.00" not in r.text


@pytest.mark.asyncio
async def test_clearing_the_course_value_falls_back_and_neither_set_is_null(client, db_session):
    uni = await _published(client, db_session)
    course = await add_course(client, uni["id"], agent_commission=TWELVE)
    org = await mk_active_org(db_session)
    await db_session.commit()

    async def effective():
        async with client_for(org["master"].email) as master:
            return (await master.get(f"{PARTNERS}/{uni['id']}")).json()["university"]["courses"][0]["agent_commission_effective"]

    assert (await effective())["source"] == "course"
    assert (await client.patch(courses_url(uni["id"], course["id"]), json={"agent_commission": None})).status_code == 200
    assert await effective() is None  # university unset + course unset
    assert (await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"amount": "900", "currency": "USD"})).status_code == 200
    assert await effective() == {"percent": None, "amount": "900.00", "currency": "USD", "note": None, "source": "university"}


@pytest.mark.asyncio
async def test_ac3_public_course_apis_never_carry_it(client, db_session):
    uni = await _published(client, db_session, agent_commission={"percent": "10"})
    await add_course(client, uni["id"], category="Agentcommission Science", agent_commission={"percent": "47.31"})
    client.cookies.clear()
    for path in (f"/api/v1/public/universities/{uni['slug']}", "/api/v1/public/overseas-courses?category=Agentcommission%20Science"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert "agent_commission" not in r.text and "47.31" not in r.text, path
