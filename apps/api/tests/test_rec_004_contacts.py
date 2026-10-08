"""rec-004 -- company contacts (spec §1-§3; DEC-SCOPE-124 C1-C7). Names are unique per test (shared database)."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Company, CompanyContact, RecContactRole
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

COMPANIES = "/api/v1/recruiter/companies"
CONTACTS = "/api/v1/recruiter/contacts"


def _name() -> str:
    return f"ABC {uuid.uuid4().hex[:8]} Technologies"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **body) -> dict:
    response = await client.post(COMPANIES, json={"name": _name(), **body})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _add(client, company_id, **body):
    return await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": "Priya", **body})


async def _role(db, name: str) -> RecContactRole:
    return await db.scalar(select(RecContactRole).where(RecContactRole.name == name))


def _primary(items):
    return [c for c in items if c["is_primary"]]


# --- create / list (AC1, AC2) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_adds_a_contact_with_every_field(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    role = await _role(db_session, "Hiring Manager")
    body = {
        "name": "Ravi Kumar",
        "designation": "Engineering Lead",
        "department": "Engineering",
        "role_id": str(role.id),
        "mobile": "98765 43210",
        "email": "Ravi@ABC.example.com",
        "linkedin_url": "linkedin.com/in/ravi",
        "preferred_channel": "whatsapp",
        "notes": "Prefers mornings\nCall before 11",
    }
    response = await client.post(f"{COMPANIES}/{company['id']}/contacts", json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["can_edit"] is True
    [contact] = data["items"]
    assert contact["name"] == "Ravi Kumar" and contact["role"]["name"] == "Hiring Manager"
    assert contact["email"] == "ravi@abc.example.com" and contact["linkedin_url"] == "https://linkedin.com/in/ravi"
    assert contact["mobile"] == "98765 43210" and contact["preferred_channel"] == "whatsapp"
    assert contact["notes"] == "Prefers mornings\nCall before 11" and contact["department"] == "Engineering"
    assert contact["is_primary"] is True and contact["active"] is True  # the first contact becomes primary (C2)
    assert contact["last_contacted_at"] is None  # C6: until rec-025/026/028
    stored = await db_session.scalar(select(CompanyContact).where(CompanyContact.id == uuid.UUID(contact["id"])))
    assert stored.mobile_normalized == "+919876543210"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.contact_create"))).all()
    assert len(audits) == 1 and audits[0].metadata_json["contact_id"] == contact["id"]
    assert "Ravi" not in str(audits[0].metadata_json)  # ids and field names only


@pytest.mark.asyncio
async def test_five_contacts_and_only_one_primary(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    for i in range(5):
        response = await _add(client, company["id"], name=f"Contact {i}", is_primary=i == 3)
        assert response.status_code == 201, response.text
    items = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert len(items) == 5
    assert [c["name"] for c in _primary(items)] == ["Contact 3"]
    assert items[0]["name"] == "Contact 3"  # primary first, then insertion order
    assert [c["name"] for c in items[1:]] == ["Contact 0", "Contact 1", "Contact 2", "Contact 4"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, message",
    [
        ({"email": "not-an-email"}, "valid email"),
        ({"mobile": "12"}, "valid mobile"),
        ({"linkedin_url": "javascript:alert(1)"}, "http"),
        ({"preferred_channel": "fax"}, "preferred_channel"),
        ({"name": "   "}, "Contact name is required"),
        ({"name": None}, "name"),
        ({"is_primary": None}, "is_primary"),
        ({"company_id": str(uuid.uuid4())}, "company_id"),
        ({"notes": "x" * 2001}, "notes"),
    ],
)
async def test_invalid_input_is_a_422(client, db_session, body, message):
    await _team(client, db_session)
    company = await _company(client)
    response = await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "Priya", **body})
    assert response.status_code == 422, response.text
    assert message in response.text


@pytest.mark.asyncio
async def test_an_inactive_role_cannot_be_set_but_can_be_kept(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    role = RecContactRole(name=f"Old role {uuid.uuid4().hex[:6]}", sort_order=10_000)  # after the seeds (test_rec_002 lists them first)
    db_session.add(role)
    await db_session.commit()
    contact = (await _add(client, company["id"], role_id=str(role.id))).json()["items"][0]
    role.active = False
    await db_session.commit()
    assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"designation": "Lead", "role_id": str(role.id)})).status_code == 200
    other = (await _add(client, company["id"], name="Second")).json()["items"]
    second = next(c for c in other if c["name"] == "Second")
    response = await client.patch(f"{CONTACTS}/{second['id']}", json={"role_id": str(role.id)})
    assert response.status_code == 422 and "contact role" in response.text
    assert (await _add(client, company["id"], role_id=str(uuid.uuid4()))).status_code == 422


# --- scope and roles (C1) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_out_of_scope_company_and_contact_are_404(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = (await _add(client, company["id"])).json()["items"][0]
    await _team(client, db_session)  # another team's recruiter
    assert (await client.get(f"{COMPANIES}/{company['id']}/contacts")).status_code == 404
    assert (await _add(client, company["id"])).status_code == 404
    assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"name": "X"})).status_code == 404
    assert (await client.patch(f"{CONTACTS}/{uuid.uuid4()}", json={"name": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_manager_and_assigned_bdm_read_but_cannot_write(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company = await _company(client, assigned_bdm_user_id=str(bdm.id))
    contact = (await _add(client, company["id"])).json()["items"][0]
    for reader in (manager, bdm):
        await login(client, reader)
        data = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()
        assert data["can_edit"] is False and len(data["items"]) == 1
        assert (await _add(client, company["id"])).status_code == 403
        assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"name": "X"})).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_writes_and_other_roles_are_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await as_role(client, db_session, "super_admin", "global")
    assert (await _add(client, company["id"])).status_code == 201
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{COMPANIES}/{company['id']}/contacts")).status_code == 403


@pytest.mark.asyncio
async def test_archived_company_contacts_are_read_only(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = (await _add(client, company["id"])).json()["items"][0]
    await client.post(f"{COMPANIES}/{company['id']}/archive")
    data = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()
    assert data["can_edit"] is False
    assert (await _add(client, company["id"])).status_code == 409
    assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"name": "X"})).status_code == 409


# --- edit / primary / deactivate (AC2, C2) --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_sends_only_changes_and_audits_field_names(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = (await _add(client, company["id"], designation="HR")).json()["items"][0]
    response = await client.patch(f"{CONTACTS}/{contact['id']}", json={"designation": "HR", "department": "People", "email": None})
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["department"] == "People"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.contact_update"))).all()
    assert [a.metadata_json["fields"] for a in audits] == [["department"]]
    assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"department": "People"})).status_code == 200  # no change, no audit
    assert len((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.contact_update"))).all()) == 1


@pytest.mark.asyncio
async def test_make_primary_moves_the_flag(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _add(client, company["id"], name="First")
    second = next(c for c in (await _add(client, company["id"], name="Second")).json()["items"] if c["name"] == "Second")
    items = (await client.patch(f"{CONTACTS}/{second['id']}", json={"is_primary": True})).json()["items"]
    assert [c["name"] for c in _primary(items)] == ["Second"]
    response = await client.patch(f"{CONTACTS}/{second['id']}", json={"is_primary": False})
    assert response.status_code == 422 and "another primary" in response.text


@pytest.mark.asyncio
async def test_deactivating_the_primary_needs_another_primary_first(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    first = (await _add(client, company["id"], name="First")).json()["items"][0]
    second = next(c for c in (await _add(client, company["id"], name="Second")).json()["items"] if c["name"] == "Second")
    response = await client.patch(f"{CONTACTS}/{first['id']}", json={"active": False})
    assert response.status_code == 409 and "primary" in response.text
    items = (await client.patch(f"{CONTACTS}/{second['id']}", json={"active": False})).json()["items"]
    assert next(c for c in items if c["name"] == "Second")["active"] is False
    response = await client.patch(f"{CONTACTS}/{second['id']}", json={"is_primary": True})
    assert response.status_code == 409 and "Reactivate" in response.text
    # The last active contact may go: it stops being primary, and the next active one becomes primary.
    items = (await client.patch(f"{CONTACTS}/{first['id']}", json={"active": False})).json()["items"]
    assert _primary(items) == [] and all(not c["active"] for c in items)
    items = (await client.patch(f"{CONTACTS}/{second['id']}", json={"active": True})).json()["items"]
    assert [c["name"] for c in _primary(items)] == ["Second"]


@pytest.mark.asyncio
async def test_concurrent_make_primary_leaves_exactly_one(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    ids = [next(c for c in (await _add(client, company["id"], name=f"C{i}")).json()["items"] if c["name"] == f"C{i}")["id"] for i in range(3)]
    responses = await asyncio.gather(*(client.patch(f"{CONTACTS}/{i}", json={"is_primary": True}) for i in ids[1:]))
    assert all(r.status_code == 200 for r in responses)
    primaries = await db_session.scalar(select(func.count()).select_from(CompanyContact).where(CompanyContact.company_id == uuid.UUID(company["id"]), CompanyContact.is_primary.is_(True)))
    assert primaries == 1


@pytest.mark.asyncio
async def test_a_company_holds_at_most_50_contacts(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    db_session.add_all(CompanyContact(company_id=uuid.UUID(company["id"]), name=f"N{i}", active=i % 2 == 0) for i in range(50))
    await db_session.commit()
    response = await _add(client, company["id"])
    assert response.status_code == 409 and "50" in response.text


# --- "+ Add Recruiter" (C7) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_recruiter_creates_the_company_and_its_primary_contact(client, db_session):
    await _team(client, db_session)
    role = await _role(db_session, "Talent Acquisition Manager")
    company = await _company(
        client,
        contact={"name": "Priya", "designation": "TA Manager", "role_id": str(role.id), "mobile": "+91 90000 00001", "email": "priya@abc.example.com", "linkedin_url": "https://linkedin.com/in/priya"},
    )
    [contact] = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert contact["name"] == "Priya" and contact["is_primary"] is True and contact["role"]["id"] == str(role.id)
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == company["id"]))).all())
    assert {"recruiter_company.create", "recruiter_company.contact_create"} <= actions


@pytest.mark.asyncio
async def test_add_recruiter_with_an_invalid_contact_creates_nothing(client, db_session):
    await _team(client, db_session)
    name = _name()
    response = await client.post(COMPANIES, json={"name": name, "contact": {"name": "Priya", "email": "nope"}})
    assert response.status_code == 422 and "valid email" in response.text
    response = await client.post(COMPANIES, json={"name": name, "contact": {"name": "Priya", "role_id": str(uuid.uuid4())}})
    assert response.status_code == 422
    assert await db_session.scalar(select(Company.id).where(Company.name == name)) is None
