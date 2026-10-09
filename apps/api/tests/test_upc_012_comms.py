"""upc-012 -- university calls, partnership message templates, WhatsApp and email (spec §1-§3; DEC-SCOPE-140 UC1-UC10; AC1-AC3, the
proposal-email positive, the unknown-placeholder negative and the no-email edge). The shared test database is never truncated, so every
template name is unique per test."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, UniversityCall, UniversityMessage
from app.services import university_comms
from tests.test_upc_006_contacts import _owned, add, contact_url, contacts_url
from tests.upc003_helpers import as_role, login, url

TEMPLATES = "/api/v1/partnership/templates"
MESSAGES = "/api/v1/partnership/messages"
CALLS = "/api/v1/partnership/calls"


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _template(client, channel="email", **over) -> dict:
    body = {"channel": channel, "name": unique("Proposal"), "body": "Dear {name}, {manager} here about {university}."}
    if channel == "email":
        body["subject"] = "Partnership proposal for {university}"
    response = await client.post(TEMPLATES, json=body | over)
    assert response.status_code == 201, response.text
    return response.json()


async def _setup(client, db, **contact_over):
    """head + owning pm + a contact; the client is signed in as the pm."""
    head, pm, other, uni = await _owned(client, db)
    await login(client, pm)
    person = await add(client, uni["id"], **contact_over)
    return head, pm, other, uni, person


# --- templates (UC4, UC5) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_head_maintains_templates_and_managers_read_active_ones(client, db_session):
    head, pm, _, _, _ = await _setup(client, db_session)
    await login(client, head)
    active = await _template(client)
    inactive = await _template(client, channel="whatsapp", subject=None)
    response = await client.patch(f"{TEMPLATES}/{inactive['id']}", json={"active": False})
    assert response.status_code == 200 and response.json()["active"] is False
    assert inactive["subject"] is None and "kind" not in active
    head_ids = {t["id"] for t in (await client.get(TEMPLATES, params={"q": active["name"]})).json()["items"]}
    assert active["id"] in head_ids
    assert (await client.get(TEMPLATES, params={"active": "false", "q": inactive["name"]})).json()["total"] == 1

    await login(client, pm)
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": unique("X"), "body": "Hi"})).status_code == 403
    assert (await client.patch(f"{TEMPLATES}/{active['id']}", json={"active": False})).status_code == 403
    assert (await client.get(TEMPLATES, params={"q": inactive["name"]})).json()["total"] == 0  # managers never see inactive rows
    assert (await client.get(TEMPLATES, params={"q": active["name"]})).json()["total"] == 1
    assert (await client.get(f"{TEMPLATES}/{inactive['id']}/preview")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "it"), ("placement_team", "it")])
async def test_other_roles_cannot_read_templates_or_communications(client, db_session, role, division):
    _, _, _, uni, person = await _setup(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(TEMPLATES)).status_code == 403
    assert (await client.get(url(uni["id"], "calls"))).status_code == 403
    assert (await client.get(url(uni["id"], "messages"))).status_code == 403
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 403


@pytest.mark.asyncio
async def test_template_rules(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    unknown = await client.post(TEMPLATES, json={"channel": "email", "name": unique("U"), "subject": "Hi {first_name}", "body": "x"})
    assert unknown.status_code == 422 and "{first_name}" in unknown.json()["detail"]  # the backlog's negative scenario
    assert (await client.post(TEMPLATES, json={"channel": "email", "name": unique("U"), "body": "no subject"})).status_code == 422
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": unique("U"), "subject": "S", "body": "x"})).status_code == 422
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": unique("U"), "body": "x" * 1001})).status_code == 422
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": unique("U"), "body": "A lone { brace is text"})).status_code == 201
    first = await _template(client)
    duplicate = await client.post(TEMPLATES, json={"channel": "email", "name": first["name"].upper(), "subject": "S", "body": "B"})
    assert duplicate.status_code == 409
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": first["name"], "body": "B"})).status_code == 201  # per channel
    assert (await client.patch(f"{TEMPLATES}/{first['id']}", json={"channel": "whatsapp"})).status_code == 422
    assert (await client.patch(f"{TEMPLATES}/{first['id']}", json={"body": "{nope}"})).status_code == 422
    assert (await client.patch(f"{TEMPLATES}/{first['id']}", json={"subject": None})).status_code == 422
    preview = (await client.get(f"{TEMPLATES}/{first['id']}/preview")).json()
    assert preview["subject"] == "Partnership proposal for University of Example" and preview["body"].startswith("Dear Priya Sharma,")


# --- render and send (UC5-UC9) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_proposal_email_from_a_template_is_queued_and_shown_with_its_status(client, db_session, smtp_on, university_emails_enqueued):
    """AC1 + the positive scenario: render with the contact's values, send, publish after the commit, list with the status."""
    head, pm, _, uni, person = await _setup(client, db_session)
    await login(client, head)
    template = await _template(client)
    await login(client, pm)
    rendered = (await client.get(f"{MESSAGES}/render", params={"template_id": template["id"], "contact_id": person["id"]})).json()
    assert rendered["subject"] == f"Partnership proposal for {uni['name']}"
    assert rendered["body"] == f"Dear Priya Raman, {pm.full_name} here about {uni['name']}." and rendered["missing"] == []
    response = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "template_id": template["id"], "subject": rendered["subject"], "body": rendered["body"]})
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["delivery_status"] == "queued" and message["template"] == {"id": template["id"], "name": template["name"]}
    assert message["contact"] == {"id": person["id"], "name": "Priya Raman"} and message["sender"]["full_name"] == pm.full_name
    assert university_emails_enqueued == [(message["id"], 0)]
    listed = (await client.get(url(uni["id"], "messages"))).json()
    assert listed["total"] == 1 and listed["items"][0]["delivery_status"] == "queued"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == message["id"]))
    assert audit.action == "university_message.create" and "body" not in audit.metadata_json and "Priya" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_whatsapp_is_logged_only_on_confirm_and_updates_last_interaction(client, db_session):
    """AC2: nothing is stored until the manager records the send; then the contact's last interaction moves."""
    _, _, _, uni, person = await _setup(client, db_session)
    contacts = (await client.get(contacts_url(uni["id"]))).json()["items"]
    assert contacts[0]["whatsapp_to"] == "919845000000" and contacts[0]["last_interaction_at"] is None
    assert (await client.get(url(uni["id"], "messages"))).json()["total"] == 0
    response = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "body": "Hi Priya"})
    assert response.status_code == 201, response.text
    assert response.json()["delivery_status"] is None
    after = (await client.get(contacts_url(uni["id"]))).json()["items"][0]
    assert after["last_interaction_at"] is not None


@pytest.mark.asyncio
async def test_a_contact_without_an_email_or_number_cannot_be_messaged(client, db_session, smtp_on):
    """The backlog's edge: no email -> 409 (and no row); no usable number -> 409. WhatsApp falls back to the phone (UC6)."""
    _, _, _, uni, person = await _setup(client, db_session, email=None, whatsapp=None, phone="12")
    assert person["email"] is None
    email = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "subject": "S", "body": "B"})
    assert email.status_code == 409 and "no email" in email.json()["detail"]
    assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "body": "B"})).status_code == 409
    fallback = await add(client, uni["id"], name="Ravi Kumar", email="ravi@abc.ac.uk", whatsapp=None, phone="98450 11111")
    listed = {c["id"]: c for c in (await client.get(contacts_url(uni["id"]))).json()["items"]}
    assert listed[fallback["id"]]["whatsapp_to"] == "919845011111"
    assert (await client.get(url(uni["id"], "messages"))).json()["total"] == 0


@pytest.mark.asyncio
async def test_email_needs_smtp(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)  # whatever the environment configures
    _, _, _, _, person = await _setup(client, db_session)
    response = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "subject": "S", "body": "B"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_a_template_must_be_active_and_of_the_channel(client, db_session):
    head, pm, _, _, person = await _setup(client, db_session)
    await login(client, head)
    email_template = await _template(client)
    await login(client, pm)
    wrong = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "template_id": email_template["id"], "body": "Hi"})
    assert wrong.status_code == 422
    assert (await client.get(f"{MESSAGES}/render", params={"template_id": str(uuid.uuid4()), "contact_id": person["id"]})).status_code == 404


# --- calls (UC1, AC3) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_call_is_logged_on_the_university_and_updates_last_interaction(client, db_session):
    _, pm, _, uni, person = await _setup(client, db_session)
    when = datetime.now(UTC) - timedelta(hours=1)
    follow_up = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    response = await client.post(
        CALLS,
        json={
            "contact_id": person["id"],
            "outcome": "connected",
            "occurred_at": when.isoformat(),
            "duration_seconds": 300,
            "notes": "Discussed the proposal.\nSend the MoU draft.",
            "next_follow_up_on": follow_up,
        },
    )
    assert response.status_code == 201, response.text
    call = response.json()
    assert call["outcome_label"] == "Connected" and call["connected"] is True and call["next_follow_up_on"] == follow_up
    assert call["contact"] == {"id": person["id"], "name": "Priya Raman"} and call["caller"]["full_name"] == pm.full_name
    assert call["university_id"] == uni["id"]
    listed = (await client.get(url(uni["id"], "calls"))).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == call["id"]
    item = (await client.get(contacts_url(uni["id"]))).json()["items"][0]
    assert datetime.fromisoformat(item["last_interaction_at"]) == datetime.fromisoformat(call["occurred_at"])
    detail = (await client.patch(contact_url(person["id"]), json={"department": "Admissions"})).json()["contact"]
    assert detail["last_interaction_at"] is not None  # the contact detail carries it too
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == call["id"]))
    assert audit.action == "university_call.create" and "notes" not in audit.metadata_json


@pytest.mark.asyncio
async def test_call_validation(client, db_session):
    _, _, _, _, person = await _setup(client, db_session)
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    past_follow_up = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
    far_follow_up = (datetime.now(UTC) + timedelta(days=400)).date().isoformat()
    for body in (
        {"outcome": "maybe"},
        {"outcome": "connected", "occurred_at": future},
        {"outcome": "connected", "occurred_at": old},
        {"outcome": "connected", "duration_seconds": 14401},
        {"outcome": "connected", "next_follow_up_on": past_follow_up},
        {"outcome": "connected", "next_follow_up_on": far_follow_up},
        {"outcome": "connected", "university_id": str(uuid.uuid4())},
    ):
        response = await client.post(CALLS, json={"contact_id": person["id"], **body})
        assert response.status_code == 422, (body, response.text)
    assert (await client.post(CALLS, json={"contact_id": str(uuid.uuid4()), "outcome": "connected"})).status_code == 404


@pytest.mark.asyncio
async def test_failed_emails_do_not_count_as_an_interaction(client, db_session):
    _, pm, _, uni, person = await _setup(client, db_session)
    row = UniversityMessage(
        university_id=uuid.UUID(uni["id"]), contact_id=uuid.UUID(person["id"]), sender_user_id=pm.id, channel="email", subject="S", body="B", delivery_status="failed", sent_at=datetime.now(UTC)
    )
    db_session.add(row)
    await db_session.commit()
    assert (await client.get(contacts_url(uni["id"]))).json()["items"][0]["last_interaction_at"] is None
    assert (await client.get(url(uni["id"], "messages"))).json()["items"][0]["delivery_status"] == "failed"


# --- who (UC3) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_writes_follow_the_contact_edit_scope_and_reads_the_partnership_roles(client, db_session):
    head, _, other, uni, person = await _setup(client, db_session)
    await client.post(CALLS, json={"contact_id": person["id"], "outcome": "busy"})
    await login(client, other)  # another manager of the same team: reads, cannot write
    assert (await client.get(url(uni["id"], "calls"))).json()["total"] == 1
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 403
    assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "body": "Hi"})).status_code == 403
    await login(client, head)  # the owning team's head writes
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 201
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 409
    assert (await client.get(url(uni["id"], "calls"))).json()["total"] == 2  # an inactive university is read-only
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(url(uni["id"], "messages"))).status_code == 200
    assert (await client.get(url(str(uuid.uuid4()), "calls"))).status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_contact_keeps_the_history_on_the_university(client, db_session):
    """UC2: upc-006's PII delete still works; the call stays, without its contact."""
    _, _, _, uni, person = await _setup(client, db_session)
    await add(client, uni["id"], name="Second Person", email="second@abc.ac.uk", is_primary=True)
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 201
    assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "body": "Hi"})).status_code == 201
    assert (await client.delete(contact_url(person["id"]))).status_code == 204
    assert (await client.get(url(uni["id"], "calls"))).json()["items"][0]["contact"] is None
    assert (await client.get(url(uni["id"], "messages"))).json()["items"][0]["contact"] is None


@pytest.mark.asyncio
async def test_daily_caps(client, db_session, monkeypatch, smtp_on, university_emails_enqueued):
    _, _, _, _, person = await _setup(client, db_session)
    monkeypatch.setattr(university_comms, "CALL_DAILY_CAP", 1)
    monkeypatch.setattr(university_comms, "DAILY_CAP", 1)
    monkeypatch.setattr(university_comms, "EMAIL_DAILY_CAP", 1)
    for status in (201, 409):
        assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == status
        assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "whatsapp", "body": "Hi"})).status_code == status
    assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "subject": "S", "body": "B"})).status_code == 201
    assert (await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "subject": "S", "body": "B"})).status_code == 429
    assert await db_session.scalar(select(UniversityCall.id).where(UniversityCall.contact_id == uuid.UUID(person["id"])))
