"""bdm-017 -- the admin lead list's attribution and the explicit conversion link (spec §5; AC1-AC3, L1, L2, L7, L9)."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, Enquiry
from tests.bdm001_helpers import login, make_user
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import ADMIN_LEADS, add_lead, as_user, conversion, student_email


@pytest.fixture(autouse=True)
def _no_crm(monkeypatch):
    from app.api import bdm_leads

    monkeypatch.setattr(bdm_leads.sync_enquiry_to_crm_task, "delay", lambda _enquiry_id: None)


async def website_enquiry(db, division: str = "it") -> Enquiry:
    enquiry = Enquiry(division=division, name="Web Lead", email=student_email(), subject="Python", message="Hello there", source="website",
                      status="new", crm_sync_status="pending")
    db.add(enquiry)
    await db.commit()
    return enquiry


async def college_lead(client, db) -> tuple[dict, dict, object]:
    """An it-division BDM lead; leaves the client signed out."""
    _, bdm, org = await bdm_with_org(client, db, "college")
    lead = await add_lead(client, org["id"])
    client.cookies.clear()
    return org, lead, bdm


def row_for(rows: list[dict], lead_id) -> dict:
    return next(r for r in rows if r["id"] == str(lead_id))


# --- the admin list (AC1, AC2) ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_bdm_lead_appears_in_the_admin_list_with_its_organization_and_bdm(client, db_session):
    org, lead, bdm = await college_lead(client, db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    rows = (await client.get(ADMIN_LEADS, params={"bdm_organization_id": org["id"]})).json()
    assert [r["id"] for r in rows] == [lead["id"]]
    row = rows[0]
    assert row["organization"] == {"id": org["id"], "code": org["code"], "name": org["name"]}
    assert row["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    assert (row["source"], row["division"], row["converted_user"]) == ("bdm", "it", None)


@pytest.mark.asyncio
async def test_website_rows_keep_their_keys_and_carry_null_attribution(client, db_session):
    enquiry = await website_enquiry(db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    row = row_for((await client.get(ADMIN_LEADS)).json(), enquiry.id)
    assert {"id", "name", "email", "phone", "division", "subject", "status", "source", "crm_sync_status"} <= row.keys()
    assert (row["organization"], row["bdm"], row["converted_user"]) == (None, None, None)


@pytest.mark.asyncio
async def test_the_organization_filter_cannot_widen_the_division_scope(client, db_session):
    org, _, _ = await college_lead(client, db_session)  # an it-division lead
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.get(ADMIN_LEADS, params={"bdm_organization_id": org["id"]})).json() == []


@pytest.mark.asyncio
async def test_public_enquiry_ignores_smuggled_attribution_and_conversion_fields(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    client.cookies.clear()
    email = f"web-{uuid.uuid4().hex[:10]}@example.com"  # the public form's EmailStr refuses the reserved .local domain
    response = await client.post("/api/v1/public/enquiries", json={
        "division": "it", "name": "Web Lead", "email": email, "subject": "Python", "message": "Hello there",
        "bdm_organization_id": org["id"], "bdm_user_id": str(uuid.uuid4()), "converted_user_id": str(uuid.uuid4())})
    assert response.status_code == 201
    row = await db_session.scalar(select(Enquiry).where(Enquiry.email == email))
    assert (row.bdm_organization_id, row.bdm_user_id, row.converted_user_id) == (None, None, None)


@pytest.mark.asyncio
async def test_patch_cannot_set_attribution_or_conversion(client, db_session):
    enquiry = await website_enquiry(db_session)
    _, _, org = await bdm_with_org(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    response = await client.patch(f"{ADMIN_LEADS}/{enquiry.id}", json={
        "status": "contacted", "bdm_organization_id": org["id"], "converted_user_id": str(student.id)})
    assert response.status_code == 200
    await db_session.refresh(enquiry)
    assert (enquiry.status, enquiry.bdm_organization_id, enquiry.converted_user_id) == ("contacted", None, None)


# --- conversion (AC3) ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_links_a_lead_to_one_student_and_unlinks_it(client, db_session):
    _, lead, _ = await college_lead(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    response = await client.post(conversion(lead["id"]), json={"student_email": student.email.upper()})
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["converted_user"] == {"id": str(student.id), "full_name": student.full_name, "email": student.email}
    assert row["status"] == "converted"
    stored = await db_session.get(Enquiry, uuid.UUID(lead["id"]))
    await db_session.refresh(stored)
    assert (stored.converted_user_id, stored.converted_by_user_id) == (student.id, admin.id) and stored.converted_at is not None
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == lead["id"]))).all()
    assert "lead.convert" in actions

    response = await client.delete(conversion(lead["id"]))
    assert response.status_code == 200
    assert (response.json()["converted_user"], response.json()["status"]) == (None, "converted")  # L2: status is left to the admin
    await db_session.refresh(stored)
    assert (stored.converted_user_id, stored.converted_at, stored.converted_by_user_id) == (None, None, None)


@pytest.mark.asyncio
async def test_the_bdm_sees_only_that_the_lead_converted(client, db_session):
    org, lead, bdm = await college_lead(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    await client.post(conversion(lead["id"]), json={"student_email": student.email})
    await as_user(client, bdm)
    item = (await client.get(f"/api/v1/bdm/organizations/{org['id']}/leads")).json()["items"][0]
    assert item["converted"] is True and "converted_user" not in item


@pytest.mark.asyncio
async def test_a_linked_lead_must_be_unlinked_before_relinking(client, db_session):
    _, lead, _ = await college_lead(client, db_session)
    first, second = await make_user(db_session, "it_student", "it"), await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(conversion(lead["id"]), json={"student_email": first.email})).status_code == 200
    response = await client.post(conversion(lead["id"]), json={"student_email": second.email})
    assert (response.status_code, response.json()["detail"]) == (409, "Unlink the current student first")


@pytest.mark.asyncio
async def test_one_student_is_linked_to_one_lead_only(client, db_session):
    _, lead, _ = await college_lead(client, db_session)
    other = await website_enquiry(db_session)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(conversion(other.id), json={"student_email": student.email})).status_code == 200
    response = await client.post(conversion(lead["id"]), json={"student_email": student.email})
    assert (response.status_code, response.json()["detail"]) == (409, "This student is already linked to another lead")


@pytest.mark.asyncio
async def test_invalid_targets_share_one_422(client, db_session):
    _, lead, _ = await college_lead(client, db_session)
    candidates = [
        "nobody-" + student_email(),
        (await make_user(db_session, "it_student", "it", active=False)).email,
        (await make_user(db_session, "trainer", "it")).email,
        (await make_user(db_session, "overseas_student", "overseas")).email,
    ]
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    for email in candidates:
        response = await client.post(conversion(lead["id"]), json={"student_email": email})
        assert (response.status_code, response.json()["detail"]) == (422, "Enter the email of an active student account in this lead's division")


@pytest.mark.asyncio
async def test_division_admins_cannot_touch_another_divisions_lead(client, db_session):
    _, lead, _ = await college_lead(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    response = await client.post(conversion(lead["id"]), json={"student_email": student.email})
    assert (response.status_code, response.json()["detail"]) == (403, "Wrong division")
    assert (await client.delete(conversion(lead["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_converts_in_any_division(client, db_session):
    enquiry = await website_enquiry(db_session, "overseas")
    student = await make_user(db_session, "overseas_student", "overseas")
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(conversion(enquiry.id), json={"student_email": student.email})).status_code == 200


@pytest.mark.asyncio
async def test_missing_lead_is_404_and_unlinking_an_unlinked_lead_is_409(client, db_session):
    enquiry = await website_enquiry(db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(conversion(uuid.uuid4()), json={"student_email": student_email()})).status_code == 404
    response = await client.delete(conversion(enquiry.id))
    assert (response.status_code, response.json()["detail"]) == (409, "This lead is not linked to a student")


@pytest.mark.asyncio
async def test_non_admins_cannot_convert(client, db_session):
    enquiry = await website_enquiry(db_session)
    for role, division in (("bdm_manager", "global"), ("counselor", "overseas"), ("it_student", "it")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.post(conversion(enquiry.id), json={"student_email": student_email()})).status_code == 403
    client.cookies.clear()
    assert (await client.post(conversion(enquiry.id), json={"student_email": student_email()})).status_code == 401


@pytest.mark.asyncio
async def test_two_admins_linking_one_student_at_once_get_one_200_and_one_409(db_session):
    first, second = await website_enquiry(db_session), await website_enquiry(db_session)
    student = await make_user(db_session, "it_student", "it")
    admin = await make_user(db_session, "it_admin", "it")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a, \
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b:
        await login(a, admin)
        await login(b, admin)
        responses = await asyncio.gather(
            a.post(conversion(first.id), json={"student_email": student.email}),
            b.post(conversion(second.id), json={"student_email": student.email}),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    linked = (await db_session.scalars(select(Enquiry.id).where(Enquiry.converted_user_id == student.id))).all()
    assert len(linked) == 1
