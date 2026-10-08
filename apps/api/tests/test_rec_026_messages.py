"""rec-026 -- recruiter message templates, WhatsApp and email (spec §1-§3; DEC-SCOPE-135 MS1-MS11): the template library and its roles,
render, send (WhatsApp logged on confirm, email queued and published after the commit), the party rules, the lists, the caps and Last
contacted. The shared test database is never truncated, so every value is unique per test."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, RecruiterMessage, RecruiterMessageTemplate
from app.services import recruiter_messages
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter
from tests.test_rec_009_candidates import body as candidate_body
from tests.test_rec_009_candidates import mail, mobile
from tests.test_rec_026_migration import _migration

TEMPLATES = "/api/v1/recruiter/templates"
MESSAGES = "/api/v1/recruiter/messages"
COMPANIES = "/api/v1/recruiter/companies"
CANDIDATES = "/api/v1/recruiter/candidates"
OUTSIDERS = [("hr_team", "it"), ("bdm", "it"), ("telecaller", "it"), ("it_admin", "it"), ("employer", "it")]


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager, name="Asha Recruiter")
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(COMPANIES, json={"name": unique("Msg Co")})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contact(client, company_id, **over) -> dict:
    name = over.pop("name", unique("Priya"))
    response = await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": name, "mobile": mobile(), "email": mail()} | over)
    assert response.status_code in (200, 201), response.text
    return next(c for c in response.json()["items"] if c["name"] == name)


async def _candidate(client, db, **over) -> dict:
    response = await client.post(CANDIDATES, json=await candidate_body(db, **over))
    assert response.status_code == 201, response.text
    return response.json()


async def _template(db, channel="whatsapp", kind=None, **over) -> RecruiterMessageTemplate:
    row = RecruiterMessageTemplate(
        channel=channel,
        kind=kind or ("follow_up" if channel == "whatsapp" else "offer_follow_up"),
        name=unique("T"),
        subject="About {company}" if channel == "email" else None,
        body="Hi {name}, {recruiter} here.",
        **over,
    )
    db.add(row)
    await db.commit()
    return row


def wa(**party) -> dict:
    return {"channel": "whatsapp", "body": "Hello there"} | party


def email(**party) -> dict:
    return {"channel": "email", "subject": "Interview", "body": "Dear candidate"} | party


# --- the template library (AC1, MS1-MS3) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_twelve_source_kinds_are_seeded_with_placeholders(client, db_session):
    await _team(client, db_session)
    seeded = (await db_session.scalars(select(RecruiterMessageTemplate).where(RecruiterMessageTemplate.name.in_([s["name"] for s in _migration.SEED])))).all()
    assert {(t.channel, t.kind) for t in seeded} == {(s["channel"], s["kind"]) for s in _migration.SEED} and len(_migration.SEED) == 12
    response = await client.get(TEMPLATES, params={"channel": "email", "q": "Interview confirmation"})
    assert response.status_code == 200
    found = next(t for t in response.json()["items"] if t["name"] == "Interview confirmation")
    assert found["kind"] == "interview_confirmation" and "{name}" in found["body"] and "{company}" in found["subject"]


@pytest.mark.asyncio
async def test_the_manager_creates_edits_and_deactivates_a_template(client, db_session):
    manager = await make_pm(db_session)
    await login(client, manager)
    name = unique("Intro")
    created = await client.post(TEMPLATES, json={"channel": "email", "kind": "company_introduction", "name": name, "subject": "Hello {company}", "body": "Dear {name},\nRegards {recruiter}"})
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["subject"] == "Hello {company}" and template["active"] is True
    patched = await client.patch(f"{TEMPLATES}/{template['id']}", json={"body": "Dear {name}", "active": False})
    assert patched.status_code == 200 and patched.json()["body"] == "Dear {name}" and patched.json()["active"] is False
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == template["id"], AuditLog.action == "recruiter_template.update"))
    assert audit.metadata_json == {"fields": ["active", "body"]}
    preview = await client.get(f"{TEMPLATES}/{template['id']}/preview")
    assert preview.status_code == 200 and preview.json()["subject"] == "Hello Acme Technologies"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"body": "Hi {student}"}, "Unknown placeholder {student}"),
        ({"kind": "company_introduction"}, "Choose a WhatsApp template kind"),
        ({"subject": "Hi"}, "Only email templates have a subject"),
        ({"body": "x" * 1001}, "at most 1000 characters"),
    ],
)
async def test_invalid_templates_are_422(client, db_session, body, detail):
    await login(client, await make_pm(db_session))
    response = await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "follow_up", "name": unique("Bad"), "body": "Hi {name}"} | body)
    assert response.status_code == 422 and detail in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_a_duplicate_name_is_409_and_the_channel_is_fixed(client, db_session):
    await login(client, await make_pm(db_session))
    name = unique("Dup")
    first = (await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "follow_up", "name": name, "body": "Hi"})).json()
    again = await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "follow_up", "name": name.upper(), "body": "Hi"})
    assert again.status_code == 409
    assert (await client.post(TEMPLATES, json={"channel": "email", "kind": "offer_follow_up", "name": name, "subject": "S", "body": "Hi"})).status_code == 201
    assert (await client.patch(f"{TEMPLATES}/{first['id']}", json={"channel": "email"})).status_code == 422


@pytest.mark.asyncio
async def test_recruiters_read_active_templates_only_and_cannot_write(client, db_session):
    inactive = await _template(db_session, active=False)
    await _team(client, db_session)
    assert (await client.get(TEMPLATES, params={"q": inactive.name})).json()["total"] == 0
    assert (await client.get(TEMPLATES, params={"q": inactive.name, "active": False})).json()["total"] == 0
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "follow_up", "name": unique("X"), "body": "Hi"})).status_code == 403
    assert (await client.patch(f"{TEMPLATES}/{inactive.id}", json={"active": True})).status_code == 403
    assert (await client.get(f"{TEMPLATES}/{inactive.id}/preview")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), OUTSIDERS)
async def test_other_roles_cannot_use_the_library(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(TEMPLATES)).status_code == 403
    assert (await client.post(TEMPLATES, json={})).status_code == 403


# --- render (MS2) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_render_fills_the_contacts_values_and_leaves_company_empty_for_a_candidate(client, db_session):
    template = await _template(db_session, "email")
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"], name=unique("Meera"))
    response = await client.get(f"{MESSAGES}/render", params={"template_id": str(template.id), "contact_id": contact["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["subject"] == f"About {company['name']}" and response.json()["body"] == f"Hi {contact['name']}, Asha Recruiter here."
    candidate = await _candidate(client, db_session, name="Rahul Verma")
    rendered = (await client.get(f"{MESSAGES}/render", params={"template_id": str(template.id), "candidate_id": candidate["id"]})).json()
    assert rendered["subject"] == "About " and rendered["body"] == "Hi Rahul Verma, Asha Recruiter here."
    assert (await client.get(f"{MESSAGES}/render", params={"template_id": str(template.id)})).status_code == 422


# --- send (AC2, AC3, MS4-MS8) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_whatsapp_to_a_contact_is_logged_on_confirm(client, db_session, caplog):
    template = await _template(db_session)
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    assert contact["whatsapp_to"] and contact["whatsapp_to"].startswith("91")
    response = await client.post(MESSAGES, json=wa(contact_id=contact["id"], template_id=str(template.id), body="Hi Priya,\nthanks"))
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["kind"] == "contact" and message["company_id"] == company["id"] and message["contact"]["id"] == contact["id"]
    assert message["template"] == {"id": str(template.id), "name": template.name} and message["delivery_status"] is None
    assert message["body"] == "Hi Priya,\nthanks" and message["sender"]["full_name"] == "Asha Recruiter"
    listed = (await client.get(f"{COMPANIES}/{company['id']}/messages")).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == message["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == message["id"]))
    assert audit.action == "recruiter_message.create" and "thanks" not in str(audit.metadata_json)
    assert "thanks" not in caplog.text
    contacts = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert next(c for c in contacts if c["id"] == contact["id"])["last_contacted_at"] is not None  # MS10


@pytest.mark.asyncio
async def test_an_interview_confirmation_email_to_a_candidate_is_queued_and_published_after_the_commit(client, db_session, smtp_on, recruiter_emails_enqueued):
    template = (await db_session.scalars(select(RecruiterMessageTemplate).where(RecruiterMessageTemplate.kind == "interview_confirmation"))).first()
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    response = await client.post(MESSAGES, json=email(candidate_id=candidate["id"], template_id=str(template.id), subject="Interview\r\nBcc: x@y.z"))
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["kind"] == "candidate" and message["candidate"]["id"] == candidate["id"] and message["delivery_status"] == "queued"
    assert message["subject"] == "Interview Bcc: x@y.z"  # one header line
    assert recruiter_emails_enqueued == [(message["id"], 0)]
    listed = (await client.get(f"{CANDIDATES}/{candidate['id']}/messages")).json()
    assert [m["id"] for m in listed["items"]] == [message["id"]]


@pytest.mark.asyncio
async def test_a_candidate_with_no_email_or_a_contact_with_no_number_is_409(client, db_session, smtp_on, recruiter_emails_enqueued):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session, email=None)
    response = await client.post(MESSAGES, json=email(candidate_id=candidate["id"]))
    assert response.status_code == 409 and response.json()["detail"] == "This candidate has no email address"
    company = await _company(client)
    contact = await _contact(client, company["id"], mobile=None)
    response = await client.post(MESSAGES, json=wa(contact_id=contact["id"]))
    assert response.status_code == 409 and response.json()["detail"] == "This contact has no mobile number"
    assert recruiter_emails_enqueued == []


@pytest.mark.asyncio
async def test_without_smtp_an_email_is_503_and_nothing_is_stored(client, db_session, recruiter_emails_enqueued):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    assert (await client.post(MESSAGES, json=email(candidate_id=candidate["id"]))).status_code == 503
    assert await db_session.scalar(select(RecruiterMessage.id).where(RecruiterMessage.candidate_id == uuid.UUID(candidate["id"]))) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        wa(),
        {"channel": "whatsapp", "body": "x", "contact_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4())},
        {"channel": "email", "body": "x", "candidate_id": str(uuid.uuid4())},
        wa(candidate_id=str(uuid.uuid4()), subject="S"),
    ],
)
async def test_the_party_and_shape_are_validated(client, db_session, payload):
    await _team(client, db_session)
    assert (await client.post(MESSAGES, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_unusable_templates_are_422(client, db_session):
    inactive = await _template(db_session, active=False)
    other_channel = await _template(db_session, "email")
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    for template in (inactive, other_channel):
        response = await client.post(MESSAGES, json=wa(candidate_id=candidate["id"], template_id=str(template.id)))
        assert response.status_code == 422 and "Choose an active WhatsApp template" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_inactive_contacts_archived_companies_and_archived_candidates_are_409(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    await client.patch(f"/api/v1/recruiter/contacts/{contact['id']}", json={"active": False})
    assert (await client.post(MESSAGES, json=wa(contact_id=contact["id"]))).status_code == 409
    candidate = await _candidate(client, db_session)
    await client.post(f"{CANDIDATES}/{candidate['id']}/archive")
    assert (await client.post(MESSAGES, json=wa(candidate_id=candidate["id"]))).status_code == 409
    other = await _company(client)
    other_contact = await _contact(client, other["id"])
    await client.post(f"{COMPANIES}/{other['id']}/archive")
    assert (await client.post(MESSAGES, json=wa(contact_id=other_contact["id"]))).status_code == 409


@pytest.mark.asyncio
async def test_scope_another_recruiters_contact_is_404_and_a_manager_reads_but_cannot_message_a_contact(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    await client.post(MESSAGES, json=wa(contact_id=contact["id"]))
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.post(MESSAGES, json=wa(contact_id=contact["id"]))).status_code == 404
    assert (await client.get(f"{COMPANIES}/{company['id']}/messages")).status_code == 404
    assert (await client.get(f"{MESSAGES}/render", params={"template_id": str(uuid.uuid4()), "contact_id": contact["id"]})).status_code == 404
    await login(client, manager)
    assert (await client.get(f"{COMPANIES}/{company['id']}/messages")).json()["total"] == 1
    assert (await client.post(MESSAGES, json=wa(contact_id=contact["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_candidate_messages_follow_the_pool(client, db_session):
    """R11: any writer messages any candidate (a manager included); hr_team reads; other roles 403; a missing candidate 404."""
    manager, _ = await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    await login(client, manager)
    assert (await client.post(MESSAGES, json=wa(candidate_id=candidate["id"]))).status_code == 201
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}/messages")).json()["total"] == 1
    assert (await client.post(MESSAGES, json=wa(candidate_id=candidate["id"]))).status_code == 403
    await as_role(client, db_session, "bdm", "it")
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}/messages")).status_code == 403
    await login(client, manager)
    assert (await client.post(MESSAGES, json=wa(candidate_id=str(uuid.uuid4())))).status_code == 404


@pytest.mark.asyncio
async def test_the_daily_caps(client, db_session, smtp_on, recruiter_emails_enqueued, monkeypatch):
    monkeypatch.setattr(recruiter_messages, "DAILY_CAP", 1)
    monkeypatch.setattr(recruiter_messages, "EMAIL_DAILY_CAP", 1)
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    assert (await client.post(MESSAGES, json=wa(candidate_id=candidate["id"]))).status_code == 201
    assert (await client.post(MESSAGES, json=wa(candidate_id=candidate["id"]))).status_code == 409
    assert (await client.post(MESSAGES, json=email(candidate_id=candidate["id"]))).status_code == 201
    assert (await client.post(MESSAGES, json=email(candidate_id=candidate["id"]))).status_code == 429


@pytest.mark.asyncio
async def test_a_failed_email_does_not_count_as_last_contacted(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    db_session.add(
        RecruiterMessage(
            company_id=uuid.UUID(company["id"]),
            contact_id=uuid.UUID(contact["id"]),
            sender_user_id=recruiter.id,
            channel="email",
            subject="S",
            body="B",
            delivery_status="failed",
            sent_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    contacts = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert next(c for c in contacts if c["id"] == contact["id"])["last_contacted_at"] is None


@pytest.mark.asyncio
async def test_candidate_detail_carries_the_whatsapp_number(client, db_session):
    await _team(client, db_session)
    number = mobile()
    candidate = await _candidate(client, db_session, mobile=f"{number[:5]} {number[5:]}")
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}")).json()["whatsapp_to"] == f"91{number}"
    no_mobile = await _candidate(client, db_session, mobile=None)
    assert no_mobile["whatsapp_to"] is None
