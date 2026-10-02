"""AGN-008 AC08/AC09 -- applications of students with no login appear, with their owner, in every shared list; School-bridged rows
stay out exactly where they were out before (spec §5.6, A6, A12)."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api import inbound
from app.models import AgentCommission, AuditLog, VisaCase
from app.services.staff_activity import _subjects
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world, mk_application, mk_school_student


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["no_login_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    w["linked_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"])
    w["school_app"] = await mk_application(db_session, agent=None, university=w["university"], school_student=await mk_school_student(db_session))
    w["rep"] = await mk_user(db_session, role="university_rep", full_name="Rep", profile={"university_id": str(w["university"].id)})
    w["admin"] = await mk_user(db_session, role="overseas_admin", full_name="Admin")
    return w


def _by_id(rows, key="id"):
    return {str(r[key]): r for r in rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["rep", "admin", "master"])
async def test_workflows_list_shows_the_no_login_owner(world, who):
    user = world[who]
    async with client_for(user.email) as c:
        response = await c.get("/api/v1/workflows/overseas/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    no_login = rows[str(world["no_login_app"].id)]
    assert no_login["student"] == world["record"].full_name and no_login["student_id"] is None
    assert rows[str(world["linked_app"].id)]["student"] == world["linked_user"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_admin_applications_shows_the_no_login_owner(world):
    async with client_for(world["admin"].email) as c:
        response = await c.get("/api/v1/admin/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    assert rows[str(world["no_login_app"].id)]["student"] == world["record"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_staff_see_their_assigned_no_login_application_and_not_others(db_session, world):
    unassigned = await mk_application(db_session, agent=world["master"], university=world["university"], record=await mk_record(db_session, agent=world["master"], full_name="Unassigned"))
    async with client_for(world["staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) in rows and str(world["linked_app"].id) in rows
    assert str(unassigned.id) not in rows
    async with client_for(world["other_staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) not in rows


@pytest.mark.asyncio
async def test_school_bridged_rows_stay_out_of_the_lists(world):
    for who in ("admin", "rep"):
        async with client_for(world[who].email) as c:
            ids = {str(r["id"]) for r in (await c.get("/api/v1/workflows/overseas/applications")).json()}
        assert str(world["school_app"].id) not in ids


PORTAL = "/api/v1/portal/overseas"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("who", "path"),
    [
        ("master", "/agent/dashboard"),
        ("master", "/agent/students"),
        ("master", "/agent/applications"),
        ("master", "/agent/documents"),
        ("rep", "/university/dashboard"),
        ("rep", "/university/applications"),
        ("rep", "/university/offer-letters"),
        ("admin", "/admin/dashboard"),
        ("admin", "/admin/applications"),
        ("admin", "/admin/visa"),
        ("admin", "/admin/reports"),
        ("admin", "/admin/commissions"),
    ],
)
async def test_agent_portal_pages_render_with_a_no_login_application(db_session, world, who, path):
    db_session.add(VisaCase(application_id=world["no_login_app"].id, status="checklist"))
    db_session.add(AgentCommission(agent_id=world["master"].id, application_id=world["no_login_app"].id, amount=0, status="estimated"))
    await db_session.commit()
    async with client_for(world[who].email) as c:
        response = await c.get(PORTAL + path)
    assert response.status_code == 200, f"{path}: {response.text}"


@pytest.mark.asyncio
async def test_rep_and_admin_portal_rows_name_the_no_login_owner(world):
    for who, path in (("rep", "/university/applications"), ("admin", "/admin/applications")):
        async with client_for(world[who].email) as c:
            rows = (await c.get(PORTAL + path)).json()["rows"]
        names = {r.get("student") for r in rows}
        assert world["record"].full_name in names, path


@pytest.mark.asyncio
async def test_commission_lists_name_the_no_login_owner(db_session, world):
    db_session.add(AgentCommission(agent_id=world["master"].id, application_id=world["no_login_app"].id, amount=0, status="estimated"))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        rows = (await c.get("/api/v1/workflows/overseas/agent/commissions")).json()
    assert world["record"].full_name in {r["student"] for r in rows}
    async with client_for(world["admin"].email) as c:
        rows = (await c.get(PORTAL + "/admin/commissions")).json()["rows"]
    assert world["record"].full_name in {r["student"] for r in rows}


@pytest.mark.asyncio
async def test_admin_enrolment_accrues_the_commission_of_a_no_login_application(db_session, world):  # AC10
    async with client_for(world["admin"].email) as c:
        response = await c.patch(f"/api/v1/workflows/overseas/applications/{world['no_login_app'].id}", json={"status": "enrolled"})
    assert response.status_code == 200, response.text
    commission = await db_session.scalar(select(AgentCommission).where(AgentCommission.application_id == world["no_login_app"].id))
    assert commission is not None and commission.agent_id == world["master"].id and commission.status == "estimated"
    async with client_for(world["master"].email) as c:
        rows = (await c.get("/api/v1/workflows/overseas/agent/commissions")).json()
    assert {(r["application_id"], r["student"]) for r in rows} >= {(str(world["no_login_app"].id), world["record"].full_name)}


@pytest.mark.asyncio
async def test_lookup_labels_the_no_login_owner(world):
    async with client_for(world["master"].email) as c:
        items = (await c.get("/api/v1/lookups/overseas-applications", params={"q": world["record"].full_name[:20]})).json()["items"]
    assert world["record"].full_name in {i["label"] for i in items}


@pytest.mark.asyncio
async def test_inbound_notify_skips_an_application_with_no_login(db_session, world):
    await inbound._notify_student(db_session, type("Email", (), {"subject": "x"})(), world["no_login_app"])  # must not raise


@pytest.mark.asyncio
async def test_staff_activity_subject_names_the_no_login_owner(db_session, world):
    row = AuditLog(user_id=world["staff"]["user"].id, action="overseas.application.create", entity_type="overseas_application", entity_id=str(world["no_login_app"].id))
    names = await _subjects(db_session, [row])
    assert names[("overseas_application", world["no_login_app"].id)].startswith(world["record"].full_name)
