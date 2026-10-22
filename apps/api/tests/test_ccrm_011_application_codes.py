"""ccrm-011 (DEC-SCOPE-238) -- every overseas application has a permanent APP- code, shown wherever applications are listed and
findable through the application lookup inside the caller's scope."""

import re

import pytest
import pytest_asyncio

from app.models import OverseasApplication
from tests.agn001_helpers import client_for, mk_user, uniq
from tests.agn008_helpers import APPS, mk_application
from tests.agn023_helpers import PORTAL, assign_world, fresh

CODE = re.compile(r"^APP-\d{6,}$")
LOOKUP = "/api/v1/lookups/overseas-applications"


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session)
    w["own"] = await mk_application(db_session, agent=None, university=w["university"], student=w["direct_student"], counselor_id=w["counselor"].id, intake=f"Own {uniq()}")
    other_student = await mk_user(db_session, role="overseas_student", full_name=f"Other Student {uniq()}")
    w["foreign"] = await mk_application(db_session, agent=None, university=w["university"], student=other_student, counselor_id=w["counselor2"].id)
    return w


@pytest.mark.asyncio
async def test_every_new_application_gets_a_distinct_code(world):
    codes = [world[k].application_code for k in ("app", "direct_app", "own", "foreign")]
    assert all(CODE.match(c) for c in codes)
    assert len(set(codes)) == 4


@pytest.mark.asyncio
async def test_a_withdrawn_application_keeps_its_code_and_it_is_never_reissued(db_session, world):
    code = world["own"].application_code
    world["own"].status = "withdrawn"
    await db_session.commit()
    assert (await fresh(db_session, world["own"])).application_code == code
    again = await mk_application(db_session, agent=None, university=world["university"], student=world["direct_student"], intake="Again")
    assert again.application_code != code and int(again.application_code[4:]) > int(code[4:])


@pytest.mark.asyncio
async def test_shared_applications_list_carries_the_code(world):
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get("/api/v1/workflows/overseas/applications")).json()
    assert {(r["id"], r["application_code"]) for r in rows} == {(str(world["own"].id), world["own"].application_code)}


@pytest.mark.asyncio
async def test_agency_list_and_detail_carry_the_code(world):
    async with client_for(world["master"].email) as c:
        items = (await c.get(APPS)).json()["items"]
        detail = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
    assert {i["application_code"] for i in items if i["id"] == str(world["app"].id)} == {world["app"].application_code}
    assert detail["application_code"] == world["app"].application_code


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "applications", "students", "admission-updates", "offer-letters"])
async def test_counselor_portal_tables_show_the_application_id(world, section):
    async with client_for(world["counselor"].email) as c:
        data = (await c.get(PORTAL.format("counselor", section))).json()
    assert {"key": "application_code", "label": "EduSphere ID"} in data["columns"]
    assert world["own"].application_code in {r["application_code"] for r in data["rows"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "applications"])
async def test_student_portal_tables_show_the_application_id(world, section):
    async with client_for(world["direct_student"].email) as c:
        data = (await c.get(PORTAL.format("student", section))).json()
    assert {"key": "application_code", "label": "EduSphere ID"} in data["columns"]
    assert {world["own"].application_code, world["direct_app"].application_code} <= {r["application_code"] for r in data["rows"]}


@pytest.mark.asyncio
async def test_university_rep_offer_letters_show_the_application_id(db_session, world):
    world["app"].offer_letter_url = "https://example.local/offer.pdf"  # UNI-001's Offer Letters rule: a letter or a legacy offer status
    await db_session.commit()
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(world["university"].id)})
    async with client_for(rep.email) as c:
        data = (await c.get(PORTAL.format("university", "offer-letters"))).json()
    assert {"key": "application_code", "label": "EduSphere ID"} in data["columns"]
    assert world["app"].application_code in {r["application_code"] for r in data["rows"]}


@pytest.mark.asyncio
async def test_agent_dashboard_shows_the_application_id(world):
    async with client_for(world["master"].email) as c:
        data = (await c.get(PORTAL.format("agent", "dashboard"))).json()
    assert {"key": "application_code", "label": "EduSphere ID"} in data["columns"]
    assert world["app"].application_code in {r["application_code"] for r in data["rows"]}


@pytest.mark.asyncio
async def test_lookup_finds_an_application_by_code_only_inside_scope(world):
    own, foreign = world["own"].application_code, world["foreign"].application_code
    async with client_for(world["counselor"].email) as c:
        found = (await c.get(LOOKUP, params={"q": own.lower()})).json()["items"]
        hidden = (await c.get(LOOKUP, params={"q": foreign})).json()["items"]
    assert [i["id"] for i in found] == [str(world["own"].id)]
    assert own in found[0]["detail"]
    assert hidden == []


@pytest.mark.asyncio
async def test_code_column_is_never_null_at_the_model(db_session, world):
    row = OverseasApplication(student_id=world["direct_student"].id, university_id=world["university"].id, status="enquiry", intake="Fresh")
    db_session.add(row)
    await db_session.commit()
    assert CODE.match(row.application_code)  # eager_defaults: the INSERT returned it, no lazy load
