"""tel-003 browser QA-01: the portal workspace lead tables (admin "Leads", counselor "My Leads") show the Lead ID as the reference,
not the row's UUID (AC1: every lead has a Lead ID people can quote)."""

import uuid

import pytest

from app.models import Enquiry
from tests.bdm001_helpers import login, make_user


async def lead(db, name: str, **over) -> Enquiry:
    row = Enquiry(**({"division": "it", "name": name, "email": f"{uuid.uuid4().hex[:8]}@example.local", "subject": "Python",
                      "message": "Hello there", "source": "website"} | over))
    db.add(row)
    await db.commit()
    return row


def lead_id_column(body: dict) -> None:
    assert body["columns"][0] == {"key": "lead_code", "label": "Lead ID"}
    assert all(c["key"] != "id" for c in body["columns"])  # the UUID is no longer shown


@pytest.mark.asyncio
async def test_the_admin_leads_workspace_shows_the_lead_id(client, db_session):
    row = await lead(db_session, f"Portal {uuid.uuid4().hex[:6]}")
    await login(client, await make_user(db_session, "it_admin", "it"))
    body = (await client.get("/api/v1/portal/it/admin/leads")).json()
    lead_id_column(body)
    listed = next(r for r in body["rows"] if r["id"] == str(row.id))
    assert listed["lead_code"] == row.lead_code


@pytest.mark.asyncio
async def test_the_counselor_my_leads_workspace_shows_the_lead_id(client, db_session):
    counselor = await make_user(db_session, "counselor", "overseas")
    row = await lead(db_session, "Mine", division="overseas", owner_id=counselor.id)
    await login(client, counselor)
    body = (await client.get("/api/v1/portal/overseas/counselor/leads")).json()
    lead_id_column(body)
    assert [r["lead_code"] for r in body["rows"]] == [row.lead_code]
