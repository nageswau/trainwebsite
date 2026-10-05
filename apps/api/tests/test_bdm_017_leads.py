"""bdm-017 -- BDM lead entry and the organization's lead list (spec §4; AC1, AC4, L3, L5, L8)."""

import logging
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import add_lead, lead_body, org_leads, student_email


@pytest.fixture
def crm_calls(monkeypatch):
    """The CRM enqueue, captured (the public form's task, called after commit)."""
    from app.api import bdm_leads

    calls: list[str] = []
    monkeypatch.setattr(bdm_leads.sync_enquiry_to_crm_task, "delay", lambda enquiry_id: calls.append(enquiry_id))
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(("bdm_type", "division"), [("college", "it"), ("school", "overseas"), ("agent", "overseas")])
async def test_created_lead_is_attributed_with_server_owned_fields(client, db_session, crm_calls, bdm_type, division):
    _, bdm, org = await bdm_with_org(client, db_session, bdm_type)
    created = await add_lead(client, org["id"], email="  Asha.N@Example.com ", note=None)
    assert created["email"] == "asha.n@example.com"
    assert (created["status"], created["converted"], created["bdm"]["id"]) == ("new", False, str(bdm.id))
    row = await db_session.get(Enquiry, uuid.UUID(created["id"]))
    assert (row.bdm_organization_id, row.bdm_user_id) == (uuid.UUID(org["id"]), bdm.id)
    assert (row.source, row.division, row.crm_sync_status, row.subject) == ("bdm", division, "pending", "B.Tech admissions")
    assert row.message == f"Lead entered by BDM at {org['name']}"
    assert row.converted_user_id is None
    assert crm_calls == [created["id"]]


@pytest.mark.asyncio
async def test_note_is_stored_as_the_message(client, db_session, crm_calls):
    _, _, org = await bdm_with_org(client, db_session)
    created = await add_lead(client, org["id"], note="Met at the career fair.\nWants hostel info.")
    assert (await db_session.get(Enquiry, uuid.UUID(created["id"]))).message == "Met at the career fair.\nWants hostel info."


@pytest.mark.asyncio
async def test_list_is_newest_first_and_total_is_exact_per_organization(client, db_session, crm_calls):
    _, _, org = await bdm_with_org(client, db_session)
    other = (await client.post("/api/v1/bdm/organizations", json={
        "org_type": "college", "name": f"Other {uuid.uuid4().hex[:8]}", "city": "Kochi", "contacts": [{"name": "Dr Rao"}]})).json()["organization"]
    ids = [(await add_lead(client, org["id"], name=f"Student {i}"))["id"] for i in range(5)]
    await add_lead(client, other["id"])
    first = (await client.get(org_leads(org["id"]), params={"limit": 2})).json()
    second = (await client.get(org_leads(org["id"]), params={"limit": 2, "offset": 2})).json()
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    assert [x["id"] for x in first["items"] + second["items"]] == list(reversed(ids))[:4]
    assert (await client.get(org_leads(other["id"]))).json()["total"] == 1


@pytest.mark.asyncio
async def test_same_email_in_the_same_organization_warns_then_saves_when_acknowledged(client, db_session, crm_calls):
    _, _, org = await bdm_with_org(client, db_session)
    email = student_email()
    first = await add_lead(client, org["id"], email=email, name="Asha Nair")
    response = await client.post(org_leads(org["id"]), json=lead_body(email=email.upper()))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert (detail["code"], detail["total"], detail["message"]) == ("possible_duplicate", 1, "This student is already a lead of this organization")
    assert [(m["id"], m["name"]) for m in detail["matches"]] == [(first["id"], "Asha Nair")]
    assert (await client.get(org_leads(org["id"]))).json()["total"] == 1  # nothing saved on the 409
    await add_lead(client, org["id"], email=email, acknowledge_duplicate=True)
    assert (await client.get(org_leads(org["id"]))).json()["total"] == 2


@pytest.mark.asyncio
async def test_the_same_email_in_another_organization_is_not_a_duplicate(client, db_session, crm_calls):
    _, _, org = await bdm_with_org(client, db_session)
    other = (await client.post("/api/v1/bdm/organizations", json={
        "org_type": "college", "name": f"Other {uuid.uuid4().hex[:8]}", "city": "Kochi", "contacts": [{"name": "Dr Rao"}]})).json()["organization"]
    email = student_email()
    await add_lead(client, org["id"], email=email)
    await add_lead(client, other["id"], email=email)


@pytest.mark.asyncio
async def test_daily_cap_refuses_with_409(client, db_session, crm_calls, monkeypatch):
    from app.services import bdm_leads as svc

    monkeypatch.setattr(svc, "DAILY_CAP", 2)
    _, _, org = await bdm_with_org(client, db_session)
    await add_lead(client, org["id"])
    await add_lead(client, org["id"])
    response = await client.post(org_leads(org["id"]), json=lead_body())
    assert (response.status_code, response.json()["detail"]) == (409, "You've added 2 leads today")


@pytest.mark.asyncio
async def test_invalid_email_is_422_and_nothing_is_saved(client, db_session, crm_calls):
    _, _, org = await bdm_with_org(client, db_session)
    response = await client.post(org_leads(org["id"]), json=lead_body(email="not-an-email"))
    assert response.status_code == 422
    assert (await client.get(org_leads(org["id"]))).json()["total"] == 0
    assert crm_calls == []


@pytest.mark.asyncio
async def test_a_broker_failure_after_commit_still_returns_201_and_keeps_the_lead_pending(client, db_session, monkeypatch, caplog):
    from app.api import bdm_leads

    def down(_enquiry_id):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(bdm_leads.sync_enquiry_to_crm_task, "delay", down)
    logging.getLogger("app.bdm").disabled = False  # a migration test earlier in the run (alembic fileConfig) disables existing loggers
    _, _, org = await bdm_with_org(client, db_session)
    with caplog.at_level(logging.WARNING, logger="app.bdm"):
        created = await add_lead(client, org["id"])
    assert (await db_session.get(Enquiry, uuid.UUID(created["id"]))).crm_sync_status == "pending"
    assert any(r.getMessage() == "bdm_lead_crm_enqueue_failed" for r in caplog.records)


@pytest.mark.asyncio
async def test_creation_is_audited_with_ids_only(client, db_session, crm_calls):
    _, bdm, org = await bdm_with_org(client, db_session)
    body = lead_body(name="Private Person")
    created = await add_lead(client, org["id"], **body)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == created["id"]))
    assert (audit.action, audit.user_id) == ("bdm_lead.created", bdm.id)
    assert audit.metadata_json == {"bdm_organization_id": org["id"]}
