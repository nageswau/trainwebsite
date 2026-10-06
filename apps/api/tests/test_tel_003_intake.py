"""tel-003 -- intake paths carry the Lead ID (spec §4; AC2, L2, L3): the public enquiry API, the CRM webhook payload and BDM leads."""

import re
import uuid

import pytest
from sqlalchemy import select

from app.models import Enquiry
from app.worker import crm_payload
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import add_lead

CODE = re.compile(r"^LD-\d{6,}$")
URL = "/api/v1/public/enquiries"


def body(**over) -> dict:
    return {"division": "it", "name": "Web Lead", "email": f"lead-{uuid.uuid4().hex[:8]}@example.com", "phone": "098765 43210",
            "subject": "Python training", "message": "Interested in the next batch."} | over


@pytest.mark.asyncio
async def test_a_website_enquiry_returns_the_same_keys_plus_its_lead_code(client, db_session):
    response = await client.post(URL, json=body())
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "status", "crm_sync_status", "lead_code"}
    assert CODE.match(data["lead_code"])
    stored = await db_session.scalar(select(Enquiry).where(Enquiry.id == uuid.UUID(data["id"])))
    assert (stored.lead_code, stored.source, stored.phone_normalized) == (data["lead_code"], "website", "+919876543210")


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["google", "walk_in", "exhibition_event"])
async def test_every_listed_source_is_accepted(client, source):
    assert (await client.post(URL, json=body(source=source))).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["tiktok", "Website", "", "facebook ads"])
async def test_a_source_outside_the_list_is_422_and_stores_nothing(client, db_session, source):
    email = f"lead-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(URL, json=body(source=source, email=email))
    assert response.status_code == 422
    assert await db_session.scalar(select(Enquiry.id).where(Enquiry.email == email)) is None


@pytest.mark.asyncio
async def test_the_crm_payload_adds_lead_code_and_keeps_every_existing_key(db_session):
    lead = Enquiry(division="it", name="Web Lead", email="crm@example.com", phone="+919876543210", subject="Python", message="Hello",
                   source="website")
    db_session.add(lead)
    await db_session.commit()
    assert crm_payload(lead) == {
        "id": str(lead.id), "lead_code": lead.lead_code, "division": "it", "name": "Web Lead", "email": "crm@example.com",
        "phone": "+919876543210", "subject": "Python", "message": "Hello", "source": "website",
    }


@pytest.mark.asyncio
async def test_a_bdm_lead_gets_a_lead_code_and_a_normalised_phone(client, db_session, monkeypatch):
    from app.api import bdm_leads

    monkeypatch.setattr(bdm_leads.sync_enquiry_to_crm_task, "delay", lambda _enquiry_id: None)
    _, _, org = await bdm_with_org(client, db_session, "college")
    lead = await add_lead(client, org["id"])
    stored = await db_session.scalar(select(Enquiry).where(Enquiry.id == uuid.UUID(lead["id"])))
    assert CODE.match(stored.lead_code)
    assert (stored.source, stored.phone_normalized) == ("bdm", "+919000011111")
