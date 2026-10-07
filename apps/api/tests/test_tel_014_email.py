"""tel-014 -- email to a lead (spec §1-§3; DEC-SCOPE-104 EM1-EM4, E1-E10): the request side -- validation, the rules, the queued row, the
publish after commit, the caps and the no-delete rule. The worker side is test_tel_014_delivery. The shared test database is never truncated,
so every assertion narrows to rows the test made."""

import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import AuditLog, LeadMessage
from app.services import lead_messages
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_user
from tests.test_tel_013_messages import MESSAGES, lead, messages_url, send, team, template

SUBJECT = "Your Python brochure secret-subject-4f"
BODY = "Dear Priya secret-email-body-7c"


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


async def email(client, lead_row, **over):
    return await client.post(messages_url(lead_row.id), json={"channel": "email", "subject": SUBJECT, "body": BODY} | over)


async def rows_for(db, lead_row) -> int:
    return await db.scalar(select(func.count()).select_from(LeadMessage).where(LeadMessage.lead_id == lead_row.id))


# --- send (AC1, E3-E6, EM4) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_email_is_queued_audited_and_published_after_the_commit(client, db_session, smtp_on, lead_emails_enqueued, caplog):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    tpl = await template(db_session, channel="email")
    await as_user(client, tel)
    with caplog.at_level(logging.INFO):
        response = await email(client, row, template_id=str(tpl.id))
    assert response.status_code == 201, response.text
    item = response.json()
    assert (item["channel"], item["subject"], item["body"], item["delivery_status"]) == ("email", SUBJECT, BODY, "queued")
    assert item["template"] == {"id": str(tpl.id), "name": tpl.name} and item["can_delete"] is False  # EM2
    assert lead_emails_enqueued == [(item["id"], 0)]  # E4: the request never waits on SMTP
    stored = await db_session.get(LeadMessage, uuid.UUID(item["id"]))
    assert stored.attempt_count == 0
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "lead_message", AuditLog.entity_id == item["id"]))).all()
    assert [a.action for a in audit] == ["lead_message.create"] and audit[0].metadata_json["channel"] == "email"
    for secret in (SUBJECT, BODY, row.email):  # E10: logs and audit carry ids only
        assert secret not in caplog.text and secret not in str(audit[0].metadata_json)


@pytest.mark.asyncio
async def test_a_free_email_has_no_template(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    response = await email(client, row)
    assert response.status_code == 201, response.text
    assert response.json()["template"] is None


@pytest.mark.asyncio
async def test_line_breaks_in_the_subject_become_spaces(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    response = await email(client, row, subject="Brochure\r\nBcc: someone@example.com\nX")
    assert response.status_code == 201, response.text
    assert response.json()["subject"] == "Brochure Bcc: someone@example.com X"  # header injection (backlog negative scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "over",
    [
        {"subject": ""},
        {"subject": "  "},
        {"subject": "\r\n"},
        {"subject": "x" * 201},
        {"subject": None},
        {"body": ""},
        {"body": "x" * 5001},
        {"body": None},
        {"to": "someone@example.com"},
    ],
)
async def test_the_subject_and_body_are_validated_and_the_recipient_is_never_the_callers(client, db_session, smtp_on, over):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    payload = {"channel": "email", "subject": SUBJECT, "body": BODY} | over
    response = await client.post(messages_url(row.id), json={k: v for k, v in payload.items() if v is not None})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_the_longest_subject_and_body_are_accepted(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await email(client, row, subject="s" * 200, body="b" * 5000)).status_code == 201


@pytest.mark.asyncio
async def test_unusable_templates_are_refused(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    for tpl_id in ((await template(db_session, channel="email", active=False)).id, (await template(db_session)).id, uuid.uuid4()):
        response = await email(client, row, template_id=str(tpl_id))
        assert response.status_code == 422, response.text
        assert any("template_id" in e["loc"] for e in response.json()["detail"])


# --- refusals (E1-E3) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_smtp_nothing_is_stored_or_published(client, db_session, lead_emails_enqueued):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    response = await email(client, row)
    assert response.status_code == 503 and response.json()["detail"] == lead_messages.EMAIL_NOT_CONFIGURED
    assert await rows_for(db_session, row) == 0 and lead_emails_enqueued == []


@pytest.mark.asyncio
async def test_a_lead_without_an_email_address_is_refused(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, email=None)
    await as_user(client, tel)
    response = await email(client, row)
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.NO_EMAIL


@pytest.mark.asyncio
async def test_only_the_leads_telecaller_emails_an_open_lead_before_handover(client, db_session, smtp_on):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, other)
    assert (await email(client, row)).status_code == 404
    await as_user(client, manager)
    assert (await email(client, row)).status_code == 403
    closed = await lead(db_session, tel, status="not_interested")
    await as_user(client, tel)
    response = await email(client, closed)
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.LEAD_CLOSED
    row.owner_id = (await make_user(db_session, "counselor", "it")).id
    await db_session.commit()
    assert (await email(client, row)).status_code == 403
    assert await rows_for(db_session, row) == 0


# --- caps (EM3) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_email_cap_answers_429_and_is_separate_from_whatsapps(client, db_session, smtp_on, monkeypatch):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    monkeypatch.setattr(lead_messages, "EMAIL_DAILY_CAP", 1)
    monkeypatch.setattr(lead_messages, "DAILY_CAP", 1)
    assert (await email(client, row)).status_code == 201
    response = await email(client, row)
    assert response.status_code == 429 and response.json()["detail"] == lead_messages.EMAIL_CAP_REACHED
    assert (await send(client, row)).status_code == 201  # the WhatsApp cap counts WhatsApp only
    assert (await send(client, row)).status_code == 409


# --- the log and delete (EM2) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_log_carries_the_delivery_status_and_an_email_cannot_be_deleted(client, db_session, smtp_on):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    sent = (await email(client, row)).json()
    await send(client, row)
    items = (await client.get(messages_url(row.id))).json()["items"]
    assert [(i["channel"], i["delivery_status"], i["can_delete"]) for i in items] == [("whatsapp", None, True), ("email", "queued", False)]
    response = await client.delete(f"{MESSAGES}/{sent['id']}")
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.EMAIL_NO_DELETE
    assert await rows_for(db_session, row) == 2
