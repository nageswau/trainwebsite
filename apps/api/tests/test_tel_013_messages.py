"""tel-013 -- WhatsApp click-to-chat + send log (spec §1-§3; DEC-SCOPE-100 WA1-WA4, D1-D9): the lead render, the send log, same-day
delete and the lead detail's `whatsapp_to`. The shared test database is never truncated, so every assertion narrows to rows the test made."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Appointment, AuditLog, Enquiry, LeadMessage, TelAsset, TelMessageTemplate
from app.services import lead_messages, telecaller_leads
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user
from tests.tel012_helpers import product, uname

LEADS = "/api/v1/telecaller/leads"
MESSAGES = "/api/v1/telecaller/messages"
SECRET_TEXT = "Hello Priya secret-body-91c"


def messages_url(lead_id) -> str:
    return f"{LEADS}/{lead_id}/messages"


def render_url(lead_id, template_id) -> str:
    return f"{LEADS}/{lead_id}/render?template_id={template_id}"


async def lead(db, telecaller=None, **over) -> Enquiry:
    values = {"division": "it", "name": "Priya Sharma", "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "98765 43210",
              "subject": "Python", "message": "Please call me", "source": "website", "status": "contacted",
              "telecaller_user_id": telecaller.id if telecaller else None} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def template(db, *, channel="whatsapp", body="Hi {name}, about {product}: {brochure_link} {appointment_time}", **over) -> TelMessageTemplate:
    values = {"channel": channel, "kind": "brochure" if channel == "whatsapp" else "course_brochure", "name": uname("Send"),
              "subject": "Your brochure" if channel == "email" else None, "body": body, "active": True} | over
    row = TelMessageTemplate(**values)
    db.add(row)
    await db.commit()
    return row


async def asset(db, *, active=True) -> TelAsset:
    uploader = await make_tl_manager(db)
    row = TelAsset(uploaded_by_user_id=uploader.id, name=uname("Brochure"), kind="brochure", storage_key=f"tel-assets/{uuid.uuid4().hex}", file_name="b.pdf", size_bytes=10,
                   active=active)
    db.add(row)
    await db.commit()
    return row


async def send(client, lead_row, body=SECRET_TEXT, **over):
    return await client.post(messages_url(lead_row.id), json={"channel": "whatsapp", "body": body} | over)


async def stored(db, lead_row, sender, sent_at) -> LeadMessage:
    """Written straight to the database -- the only way to have a send from an earlier day."""
    row = LeadMessage(lead_id=lead_row.id, sender_user_id=sender.id, channel="whatsapp", body="old", sent_at=sent_at)
    db.add(row)
    await db.commit()
    return row


# --- whatsapp_to (D1, AC1) -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("whatsapp", "phone", "expected"), [
    ("+44 7700 900123", "9876543210", "447700900123"),  # the WhatsApp number wins
    (None, "098765-43210", "919876543210"),  # mobile, +91 default
    ("12", "9876543210", "919876543210"),  # an unusable WhatsApp number falls back to the mobile
    (None, None, None),
    ("abc", "123", None),
])
def test_whatsapp_to_prefers_the_whatsapp_number_then_the_mobile(whatsapp, phone, expected):
    assert telecaller_leads.whatsapp_to(Enquiry(whatsapp_number=whatsapp, phone=phone)) == expected


@pytest.mark.asyncio
async def test_the_lead_detail_carries_whatsapp_to(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, whatsapp_number="+44 7700 900123")
    await as_user(client, tel)
    response = await client.get(f"{LEADS}/{row.id}")
    assert response.status_code == 200, response.text
    assert response.json()["whatsapp_to"] == "447700900123"


# --- render (inherited tel-012 C2, D5) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_render_fills_the_lead_values_the_brochure_link_and_the_open_appointment(client, db_session):
    _, tel, _ = await team(db_session)
    prod = await product(db_session)
    row = await lead(db_session, tel, product_id=prod.id)
    brochure = await asset(db_session)
    tpl = await template(db_session, product_id=prod.id, asset_id=brochure.id)
    db_session.add(Appointment(division="it", lead_id=row.id, scheduled_at=datetime(2026, 9, 14, 5, 0, tzinfo=UTC), appointment_type="career_counselling",
                               status="scheduled"))
    await db_session.commit()
    await as_user(client, tel)
    response = await client.get(render_url(row.id, tpl.id))
    assert response.status_code == 200, response.text
    body = response.json()
    link = body["brochure_link"]["url"]
    assert "/api/v1/public/telecaller-assets/" in link
    assert body["body"] == f"Hi Priya Sharma, about {prod.name}: {link} Mon 14 Sept 2026, 10:30 AM"
    assert body["subject"] is None and body["product_mismatch"] is False
    assert body["template"] == {"id": str(tpl.id), "name": tpl.name, "channel": "whatsapp", "kind": "brochure"}


@pytest.mark.asyncio
async def test_render_without_lead_product_uses_the_template_product_and_leaves_missing_values_empty(client, db_session):
    _, tel, _ = await team(db_session)
    prod = await product(db_session)
    row = await lead(db_session, tel)
    tpl = await template(db_session, product_id=prod.id, asset_id=(await asset(db_session, active=False)).id)
    await as_user(client, tel)
    body = (await client.get(render_url(row.id, tpl.id))).json()
    assert body["body"] == f"Hi Priya Sharma, about {prod.name}:  " and body["brochure_link"] is None
    assert body["product_mismatch"] is False  # the lead has no product to mismatch


@pytest.mark.asyncio
async def test_render_flags_another_products_template_as_a_warning_only(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, product_id=(await product(db_session)).id)
    tpl = await template(db_session, product_id=(await product(db_session)).id)
    await as_user(client, tel)
    response = await client.get(render_url(row.id, tpl.id))
    assert response.status_code == 200 and response.json()["product_mismatch"] is True


@pytest.mark.asyncio
async def test_render_refuses_an_inactive_or_unknown_template_and_an_out_of_scope_lead(client, db_session):
    _, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    inactive = await template(db_session, active=False)
    assert (await client.get(render_url(row.id, inactive.id))).status_code == 404
    assert (await client.get(render_url(row.id, uuid.uuid4()))).status_code == 404
    theirs = await lead(db_session, other)
    assert (await client.get(render_url(theirs.id, (await template(db_session)).id))).status_code == 404


@pytest.mark.asyncio
async def test_a_manager_may_render_for_a_reports_lead_and_an_email_template_renders_its_subject(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    tpl = await template(db_session, channel="email", subject="For {name}", body="Dear {name}")
    await as_user(client, manager)
    body = (await client.get(render_url(row.id, tpl.id))).json()
    assert (body["subject"], body["body"]) == ("For Priya Sharma", "Dear Priya Sharma")


# --- send (AC2, WA1-WA4, D2-D8) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sending_from_a_template_records_the_full_text_the_template_and_the_time(client, db_session, caplog):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    tpl = await template(db_session)
    await as_user(client, tel)
    before = datetime.now(UTC) - timedelta(seconds=5)
    with caplog.at_level(logging.INFO):
        response = await send(client, row, template_id=str(tpl.id))
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["channel"] == "whatsapp" and item["body"] == SECRET_TEXT and item["subject"] is None
    assert item["template"] == {"id": str(tpl.id), "name": tpl.name}
    assert item["sender"]["id"] == str(tel.id) and item["can_delete"] is True
    assert datetime.fromisoformat(item["sent_at"]) >= before
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "lead_message", AuditLog.entity_id == item["id"]))).all()
    assert actions == ["lead_message.create"]
    assert SECRET_TEXT not in caplog.text and "98765" not in caplog.text  # WA1: logs carry ids only
    stage = await db_session.scalar(select(Enquiry.status).where(Enquiry.id == row.id).execution_options(populate_existing=True))
    assert stage == "contacted"  # D7: no stage effect


@pytest.mark.asyncio
async def test_a_free_message_has_no_template_and_a_renamed_template_keeps_its_sent_name(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    tpl = await template(db_session)
    await as_user(client, tel)
    free = (await send(client, row)).json()
    assert free["template"] is None
    sent_name = tpl.name
    assert (await send(client, row, template_id=str(tpl.id))).status_code == 201
    tpl.name = uname("Renamed")
    await db_session.commit()
    page = (await client.get(messages_url(row.id))).json()
    assert page["total"] == 2 and page["items"][0]["template"]["name"] == sent_name  # D6 snapshot, newest first


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["", "   ", "x" * 1001])
async def test_the_text_must_be_one_to_a_thousand_characters(client, db_session, body):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await send(client, row, body=body)).status_code == 422


@pytest.mark.asyncio
async def test_email_channel_and_unusable_templates_are_refused(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await send(client, row, channel="email")).status_code == 422  # tel-014: an email needs a subject
    for tpl_id in ((await template(db_session, active=False)).id, (await template(db_session, channel="email")).id, uuid.uuid4()):
        response = await send(client, row, template_id=str(tpl_id))
        assert response.status_code == 422, response.text
        assert any("template_id" in e["loc"] for e in response.json()["detail"])


@pytest.mark.asyncio
async def test_a_lead_without_any_usable_number_cannot_be_messaged(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, phone=None, whatsapp_number=None)
    await as_user(client, tel)
    response = await send(client, row)
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.NO_NUMBER


@pytest.mark.asyncio
async def test_a_closed_lead_is_refused(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="not_interested")
    await as_user(client, tel)
    response = await send(client, row)
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.LEAD_CLOSED


@pytest.mark.asyncio
async def test_only_the_leads_telecaller_sends_before_handover(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, other)
    assert (await send(client, row)).status_code == 404
    await as_user(client, manager)
    assert (await send(client, row)).status_code == 403
    counselor = await make_user(db_session, "counselor", "it")
    row.owner_id = counselor.id
    await db_session.commit()
    await as_user(client, tel)
    assert (await send(client, row)).status_code == 403
    assert (await client.get(messages_url(row.id))).status_code == 200  # read-only access stays


@pytest.mark.asyncio
async def test_other_roles_cannot_read_the_log(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(messages_url(row.id))).status_code in (403, 404)


@pytest.mark.asyncio
async def test_the_daily_cap_refuses_the_next_send(client, db_session, monkeypatch):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    monkeypatch.setattr(lead_messages, "DAILY_CAP", 1)
    assert (await send(client, row)).status_code == 201
    response = await send(client, row)
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.CAP_REACHED


@pytest.mark.asyncio
async def test_a_manager_reads_the_log_without_delete(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    await send(client, row)
    await as_user(client, manager)
    page = (await client.get(messages_url(row.id))).json()
    assert page["total"] == 1 and page["items"][0]["can_delete"] is False


# --- delete (WA3) ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_sender_deletes_todays_send_with_an_audit_row(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    item = (await send(client, row)).json()
    assert (await client.delete(f"{MESSAGES}/{item['id']}")).status_code == 204
    assert (await client.get(messages_url(row.id))).json()["total"] == 0
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "lead_message", AuditLog.entity_id == item["id"]))).all()
    assert sorted(actions) == ["lead_message.create", "lead_message.delete"]


@pytest.mark.asyncio
async def test_an_earlier_days_send_cannot_be_deleted(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    old = await stored(db_session, row, tel, datetime.now(UTC) - timedelta(days=2))
    await as_user(client, tel)
    page = (await client.get(messages_url(row.id))).json()
    assert page["items"][0]["can_delete"] is False
    response = await client.delete(f"{MESSAGES}/{old.id}")
    assert response.status_code == 409 and response.json()["detail"] == lead_messages.NOT_TODAY


@pytest.mark.asyncio
async def test_only_the_sender_deletes_and_out_of_scope_reads_as_missing(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    item = (await send(client, row)).json()
    await as_user(client, manager)
    assert (await client.delete(f"{MESSAGES}/{item['id']}")).status_code == 403
    await as_user(client, other)
    assert (await client.delete(f"{MESSAGES}/{item['id']}")).status_code == 404
    assert (await client.delete(f"{MESSAGES}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_a_handed_over_leads_send_cannot_be_deleted(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    item = (await send(client, row)).json()
    row.owner_id = (await make_user(db_session, "counselor", "it")).id
    await db_session.commit()
    assert (await client.delete(f"{MESSAGES}/{item['id']}")).status_code == 403
