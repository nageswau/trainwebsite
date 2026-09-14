"""ADM-002 -- CRM-linked enquiry/lead management.

`GET`/`PATCH /admin/leads` already existed and already got this right: the list returns
every enquiry regardless of `crm_sync_status` (no filter excludes a failed sync), and
`update_lead` never gates on sync status either -- untested until now. Covers the ACs
directly: a failed-sync enquiry stays visible and actionable (ADM-002-AC02), routing
(status/owner_id) works, and RBAC.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Enquiry, User


async def _create_admin(db_session, *, division: str = "it") -> User:
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Leads Admin",
        role="it_admin",
        division=division,
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_enquiry(db_session, *, division: str = "it", crm_sync_status: str = "pending") -> Enquiry:
    enquiry = Enquiry(
        division=division,
        name="Prospective Student",
        email=f"lead-{uuid.uuid4().hex[:8]}@example.local",
        phone="9999999999",
        subject="Python Full Stack",
        message="Interested in the programme.",
        source="website",
        status="new",
        crm_sync_status=crm_sync_status,
    )
    db_session.add(enquiry)
    await db_session.commit()
    return enquiry


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_failed_sync_enquiry_still_appears_in_the_leads_list(client, db_session):
    """ADM-002-AC02: remains visible regardless of sync status."""
    admin = await _create_admin(db_session)
    failed = await _create_enquiry(db_session, crm_sync_status="failed")
    await _login(client, admin.email)

    response = await client.get("/api/v1/admin/leads")
    assert response.status_code == 200
    listed = next(item for item in response.json() if item["id"] == str(failed.id))
    assert listed["crm_sync_status"] == "failed"


@pytest.mark.asyncio
async def test_a_failed_sync_enquiry_is_still_actionable(client, db_session):
    """ADM-002-AC02: remains actionable regardless of sync status -- routing still works."""
    admin = await _create_admin(db_session)
    failed = await _create_enquiry(db_session, crm_sync_status="failed")
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/leads/{failed.id}", json={"status": "contacted"})
    assert response.status_code == 200

    await db_session.refresh(failed)
    assert failed.status == "contacted"
    assert failed.crm_sync_status == "failed"  # routing never touches sync status


@pytest.mark.asyncio
async def test_admin_can_route_an_enquiry_to_an_owner(client, db_session):
    admin = await _create_admin(db_session)
    enquiry = await _create_enquiry(db_session)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/leads/{enquiry.id}", json={"status": "contacted", "owner_id": str(admin.id)})
    assert response.status_code == 200

    await db_session.refresh(enquiry)
    assert enquiry.status == "contacted"
    assert enquiry.owner_id == admin.id


@pytest.mark.asyncio
async def test_admin_cannot_route_an_enquiry_outside_their_division(client, db_session):
    admin = await _create_admin(db_session, division="it")
    overseas_enquiry = await _create_enquiry(db_session, division="overseas")
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/leads/{overseas_enquiry.id}", json={"status": "contacted"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_routing_a_nonexistent_lead_404s(client, db_session):
    admin = await _create_admin(db_session)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/leads/{uuid.uuid4()}", json={"status": "contacted"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_non_admin_cannot_view_or_route_leads(client, db_session):
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Not An Admin",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    enquiry = await _create_enquiry(db_session)
    await db_session.commit()
    await _login(client, student.email)

    assert (await client.get("/api/v1/admin/leads")).status_code == 403
    assert (await client.patch(f"/api/v1/admin/leads/{enquiry.id}", json={"status": "contacted"})).status_code == 403


@pytest.mark.asyncio
async def test_routing_a_lead_requires_authentication(client):
    response = await client.patch(f"/api/v1/admin/leads/{uuid.uuid4()}", json={"status": "contacted"})
    assert response.status_code == 401
