"""tel-005 -- a website enquiry from a known person attaches to the existing lead (spec §1, §3; T12, I3, I4, R1, R4). The public reply
keeps its keys and constant values either way, so it never tells an anonymous caller that the person is already known."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.api import public
from app.models import Enquiry, LeadEnquiry

URL = "/api/v1/public/enquiries"


def mobile() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


def mail() -> str:
    return f"t5p-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def queued(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(public.sync_enquiry_to_crm_task, "delay", calls.append)
    return calls


def form(**over) -> dict:
    return {"division": "it", "name": "Web Visitor", "email": mail(), "phone": mobile(), "subject": "Data Science",
            "message": "Please send the fees.", "metadata": {"utm_source": "ad"}} | over


async def existing(db, **over) -> Enquiry:
    values = {"division": "it", "name": "Known Person", "email": mail(), "phone": mobile(), "subject": "Python", "message": "First",
              "source": "instagram", "status": "contacted"} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def count(db, **where) -> int:
    return await db.scalar(select(func.count()).select_from(Enquiry).filter_by(**where))


@pytest.mark.asyncio
async def test_a_known_email_attaches_with_the_same_reply_and_no_webhook(client, db_session, queued):
    old = await existing(db_session)
    response = await client.post(URL, json=form(email=old.email.upper(), phone=None))
    assert response.status_code == 201
    data = response.json()
    assert data == {"id": str(old.id), "status": "new", "crm_sync_status": "pending", "lead_code": old.lead_code}  # I3
    assert queued == []  # I4: per lead
    assert await count(db_session, email=old.email) == 1
    [row] = (await db_session.scalars(select(LeadEnquiry).where(LeadEnquiry.lead_id == old.id))).all()
    assert (row.subject, row.message, row.source, row.created_by_user_id, row.metadata_json) == (
        "Data Science", "Please send the fees.", "website", None, {"utm_source": "ad"})
    await db_session.refresh(old)
    assert (old.status, old.subject) == ("contacted", "Python")  # the lead itself is untouched


@pytest.mark.asyncio
async def test_a_known_mobile_in_another_format_attaches(client, db_session, queued):
    number = mobile()
    old = await existing(db_session, phone=f"+91{number}")
    response = await client.post(URL, json=form(phone=f"0{number}"))
    assert response.status_code == 201 and response.json()["id"] == str(old.id)
    assert queued == []


@pytest.mark.asyncio
async def test_an_unknown_person_is_a_new_lead_queued_once(client, db_session, queued):
    payload = form()
    response = await client.post(URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "status", "crm_sync_status", "lead_code"} and data["status"] == "new"
    assert queued == [data["id"]]
    assert await count(db_session, email=payload["email"]) == 1


@pytest.mark.asyncio
async def test_the_newest_matching_lead_wins(client, db_session, queued):
    address = mail()
    await existing(db_session, email=address, created_at=datetime.now(UTC) - timedelta(days=3))
    newer = await existing(db_session, email=address)
    response = await client.post(URL, json=form(email=address, phone=None))
    assert response.json()["id"] == str(newer.id)
