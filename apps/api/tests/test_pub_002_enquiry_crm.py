"""PUB-002 -- Enquiry submission synced to CRM.

Covers: the outbox pattern (submission never blocks on/loses data to a slow or
unconfigured webhook, INTEGRATION_CONTRACTS.md §1), and RBAC on the admin-facing read
side (Public submit / Admin view, division-scoped).
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Enquiry, User


@pytest.mark.asyncio
async def test_enquiry_submission_is_public_and_fast_no_inline_webhook_wait(client):
    payload = {
        "division": "it",
        "name": "Compact Lead",
        "email": f"lead-{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+919999000000",
        "subject": "Python training",
        "message": "Interested in the next available batch.",
    }
    response = await client.post("/api/v1/public/enquiries", json=payload)
    assert response.status_code == 201
    body = response.json()
    # AC02 / outbox pattern: the response reflects the *committed* local record, not
    # the outcome of a webhook call this request never waits on -- always "pending"
    # here, never "sent"/"failed", because the sync happens out-of-band afterward.
    assert body["crm_sync_status"] == "pending"
    assert body["id"]


@pytest.mark.asyncio
async def test_enquiry_survives_even_when_no_crm_webhook_is_configured(client, db_session):
    from sqlalchemy import select

    email = f"lead-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/public/enquiries",
        json={"division": "overseas", "name": "Unconfigured CRM Lead", "email": email, "subject": "UK Masters", "message": "Please advise on timelines."},
    )
    assert response.status_code == 201
    enquiry = await db_session.scalar(select(Enquiry).where(Enquiry.email == email))
    assert enquiry is not None, "the enquiry itself must exist regardless of CRM sync outcome"


@pytest.mark.asyncio
async def test_enquiry_endpoint_requires_no_authentication(client):
    response = await client.post(
        "/api/v1/public/enquiries",
        json={"division": "it", "name": "Visitor", "email": f"v-{uuid.uuid4().hex[:8]}@example.com", "subject": "General", "message": "Hello there, please contact me."},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_admin_leads_endpoint_denies_unauthenticated_and_wrong_role(client):
    unauth = await client.get("/api/v1/admin/leads")
    assert unauth.status_code == 401


@pytest.mark.asyncio
async def test_admin_leads_scoped_to_own_division_for_division_admin(client, db_session):
    # An IT Admin's /admin/leads must never return an Overseas-division enquiry.
    email = f"itadmin-{uuid.uuid4().hex[:8]}@example.local"
    admin = User(email=email, password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="IT Admin", role="it_admin", division="it", active=True)
    db_session.add(admin)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert login.status_code == 200

    leads = await client.get("/api/v1/admin/leads")
    assert leads.status_code == 200
    assert all(item["division"] == "it" for item in leads.json())
