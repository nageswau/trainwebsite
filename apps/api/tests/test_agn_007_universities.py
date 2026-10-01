"""AGN-007 -- the agency's own universities (spec §5.1; AC06, AC09, AC10 universities cap, AC11)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudentShortlistEntry, AgentUniversity, AuditLog
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Uni Agency")
    other = await mk_active_org(db_session, name="Uni Other Agency")
    staff = await mk_staff(db_session, ctx["org"], full_name="Uni Staff")
    return ctx | {"other": other, "staff": staff, "tag": uuid.uuid4().hex[:8]}


async def _add(client, name: str, country: str = "Ireland", **extra):
    return await client.post(UNIVERSITIES, json={"name": name, "country": country, **extra})


@pytest.mark.asyncio
async def test_master_adds_edits_and_deletes_with_audit(db_session, agency):  # AGN-007-AC06
    async with client_for(agency["master"].email) as m:
        created = await _add(m, f"Trinity {agency['tag']}", city="Dublin", entry_requirements="IELTS 6.5")
        assert created.status_code == 201, created.text
        body = created.json()["university"]
        assert set(body) == {"id", "name", "country", "city", "entry_requirements", "created_at", "updated_at"}
        uid = body["id"]
        edited = await m.patch(f"{UNIVERSITIES}/{uid}", json={"city": None})
        assert edited.status_code == 200 and edited.json()["university"]["city"] is None
        assert (await m.delete(f"{UNIVERSITIES}/{uid}")).status_code == 204
        assert (await m.delete(f"{UNIVERSITIES}/{uid}")).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == uid).order_by(AuditLog.created_at))).all()
    assert actions == ["agent_university.create", "agent_university.update", "agent_university.delete"]
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == uid, AuditLog.action == "agent_university.update"))).one()
    assert meta == {"fields": ["city"]}  # field names, never values


@pytest.mark.asyncio
async def test_staff_view_but_cannot_write(db_session, agency):  # AGN-007-AC06
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"Staff Visible {agency['tag']}")).json()["university"]["id"]
    async with client_for(agency["staff"]["user"].email) as s:
        listing = await s.get(UNIVERSITIES)
        assert listing.status_code == 200 and uid in [u["id"] for u in listing.json()["items"]]
        refused = [
            (await _add(s, "Staff Made"), "Only an agency Master can add universities"),
            (await s.patch(f"{UNIVERSITIES}/{uid}", json={"city": "X"}), "Only an agency Master can edit universities"),
            (await s.delete(f"{UNIVERSITIES}/{uid}"), "Only an agency Master can delete universities"),
        ]
    for response, detail in refused:
        assert response.status_code == 403 and response.json()["detail"] == detail
    assert await db_session.scalar(select(func.count()).select_from(AgentUniversity).where(AgentUniversity.name == "Staff Made")) == 0
    row = await db_session.get(AgentUniversity, uuid.UUID(uid), populate_existing=True)
    assert row.city is None
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == uid)) == 1  # the create only


@pytest.mark.asyncio
async def test_other_agency_cannot_see_or_touch(agency):  # AGN-007-AC04 (universities)
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"Private {agency['tag']}")).json()["university"]["id"]
    async with client_for(agency["other"]["master"].email) as o:
        assert uid not in [u["id"] for u in (await o.get(UNIVERSITIES, params={"limit": 100})).json()["items"]]
        assert (await o.patch(f"{UNIVERSITIES}/{uid}", json={"city": "X"})).status_code == 404
        assert (await o.delete(f"{UNIVERSITIES}/{uid}")).status_code == 404
        assert (await _add(o, f"Private {agency['tag']}")).status_code == 201  # same name in another agency is fine


@pytest.mark.asyncio
async def test_duplicate_name_and_country_is_409(agency):  # AGN-007-AC09
    async with client_for(agency["master"].email) as m:
        assert (await _add(m, f"Dup {agency['tag']}")).status_code == 201
        twin = await _add(m, f"DUP {agency['tag']}".upper(), "IRELAND")
        assert twin.status_code == 409 and twin.json()["detail"] == "This university is already in your agency's list"
        other = (await _add(m, f"Other {agency['tag']}")).json()["university"]["id"]
        renamed = await m.patch(f"{UNIVERSITIES}/{other}", json={"name": f"dup {agency['tag']}"})
        assert renamed.status_code == 409


@pytest.mark.asyncio
async def test_delete_in_use_is_409_and_keeps_everything(db_session, agency):  # AGN-007-AC09
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"In Use {agency['tag']}")).json()["university"]["id"]
    student = await mk_record(db_session, agent=agency["master"], full_name="In Use Student")
    db_session.add(AgentStudentShortlistEntry(agent_student_id=student.id, agent_university_id=uuid.UUID(uid)))
    await db_session.commit()
    async with client_for(agency["master"].email) as m:
        response = await m.delete(f"{UNIVERSITIES}/{uid}")
    assert response.status_code == 409
    assert response.json()["detail"] == "This university is on 1 shortlist entry; remove it from them first"
    assert await db_session.get(AgentUniversity, uuid.UUID(uid), populate_existing=True) is not None


@pytest.mark.asyncio
async def test_university_cap_is_422(db_session, agency, monkeypatch):  # AGN-007-AC10 (agency cap)
    monkeypatch.setattr(service, "MAX_UNIVERSITIES_PER_AGENCY", 2)
    async with client_for(agency["master"].email) as m:
        assert (await _add(m, f"Cap1 {agency['tag']}")).status_code == 201
        assert (await _add(m, f"Cap2 {agency['tag']}")).status_code == 201
        third = await _add(m, f"Cap3 {agency['tag']}")
    assert third.status_code == 422 and third.json()["detail"] == "Your agency has reached the limit of 2 universities"


@pytest.mark.asyncio
async def test_list_pages_searches_and_bounds(agency):  # AGN-007-AC11
    async with client_for(agency["master"].email) as m:
        for n in ("Beta", "alpha", "Gamma"):
            await _add(m, f"{n} {agency['tag']}", city="Cork" if n == "Gamma" else None)
        page = (await m.get(UNIVERSITIES, params={"q": agency["tag"], "limit": 2})).json()
        assert [u["name"] for u in page["items"]] == [f"alpha {agency['tag']}", f"Beta {agency['tag']}"] and page["total"] == 3
        assert (await m.get(UNIVERSITIES, params={"q": "Cork"})).json()["total"] >= 1
        assert (await m.get(UNIVERSITIES, params={"q": agency["tag"], "offset": 50})).json() == {"items": [], "total": 3, "limit": 20, "offset": 50}
        assert (await m.get(UNIVERSITIES, params={"q": "100%_"})).status_code == 200  # escaped, not a wildcard
        for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            assert (await m.get(UNIVERSITIES, params=bad)).status_code == 422


@pytest.mark.asyncio
async def test_inactive_agency_and_non_agents_are_refused(db_session, agency):
    from app.models import AgentOrg
    from tests.agn001_helpers import mk_user

    org = await db_session.get(AgentOrg, agency["other"]["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(agency["other"]["master"].email) as o:
        assert (await o.get(UNIVERSITIES)).status_code == 403
    admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(admin.email) as a:
        assert (await a.get(UNIVERSITIES)).status_code == 403


@pytest.mark.asyncio
async def test_portal_section_exists_for_both_roles(agency):
    for email in (agency["master"].email, agency["staff"]["user"].email):
        async with client_for(email) as c:
            body = (await c.get("/api/v1/portal/overseas/agent/universities")).json()
        assert body["title"] == "Universities" and body["rows"] == []
